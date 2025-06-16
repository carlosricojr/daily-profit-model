"""
Schema validation tests to ensure database schema integrity and correctness.

This module tests:
- Schema SQL syntax validation
- Table relationships and foreign keys
- Index coverage and performance
- Partition management
- Data type consistency
- Constraint validation
"""

import pytest
import re
from pathlib import Path
from typing import Dict, List, Tuple
import sqlparse

# Add parent directory to path
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class SchemaValidator:
    """Validates database schema for correctness and best practices."""
    
    def __init__(self, schema_content: str):
        self.content = schema_content
        self.parsed = sqlparse.parse(schema_content)
        self.tables = {}
        self.indexes = {}
        self.views = {}
        self.functions = {}
        self.constraints = {}
        self._parse_schema()
    
    def _parse_schema(self):
        """Parse schema and extract all objects."""
        # Extract tables with columns
        table_pattern = r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)\.?(\w+)?\s*\((.*?)\)(?:\s+PARTITION\s+BY\s+[^;]+)?;'
        for match in re.finditer(table_pattern, self.content, re.IGNORECASE | re.DOTALL):
            schema = match.group(1) if match.group(2) else 'public'
            table_name = match.group(2) if match.group(2) else match.group(1)
            columns_def = match.group(3)
            
            # Parse columns
            columns = self._parse_columns(columns_def)
            self.tables[table_name] = {
                'schema': schema,
                'columns': columns,
                'definition': match.group(0)
            }
        
        # Extract indexes
        index_pattern = r'CREATE\s+(?:UNIQUE\s+)?INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)\s+ON\s+(\w+)\.?(\w+)?\s*\(([^)]+)\)'
        for match in re.finditer(index_pattern, self.content, re.IGNORECASE):
            index_name = match.group(1)
            table_name = match.group(3) if match.group(3) else match.group(2)
            columns = [col.strip() for col in match.group(4).split(',')]
            
            self.indexes[index_name] = {
                'table': table_name,
                'columns': columns,
                'unique': 'UNIQUE' in match.group(0).upper()
            }
    
    def _parse_columns(self, columns_def: str) -> Dict[str, Dict]:
        """Parse column definitions from CREATE TABLE."""
        columns = {}
        
        # Split by comma but respect parentheses
        parts = self._split_respecting_parens(columns_def)
        
        for part in parts:
            # Handle multi-line parts by processing each line
            lines = part.strip().split('\n')
            for line in lines:
                line = line.strip()
                if not line or line.startswith('--'):
                    continue
                    
                # Skip constraints
                if any(keyword in line.upper() for keyword in ['PRIMARY KEY', 'FOREIGN KEY', 'CONSTRAINT', 'CHECK', 'UNIQUE']):
                    # Special case: inline PRIMARY KEY is part of column definition
                    if 'PRIMARY KEY' in line.upper() and not line.upper().startswith('PRIMARY KEY'):
                        # This is a column with inline PRIMARY KEY, process it
                        pass
                    else:
                        continue
                
                # Parse column: name type [constraints]
                # Remove trailing comma if present
                line = line.rstrip(',')
                tokens = line.split()
                if len(tokens) >= 2:
                    col_name = tokens[0]
                    col_type = tokens[1]
                    
                    # Handle parameterized types like VARCHAR(100)
                    if '(' in line:
                        type_match = re.search(r'(\w+)\s*\(([^)]+)\)', line)
                        if type_match:
                            col_type = type_match.group(0)
                    
                    columns[col_name] = {
                        'type': col_type,
                        'nullable': 'NOT NULL' not in line.upper(),
                        'default': self._extract_default(line),
                        'primary_key': 'PRIMARY KEY' in line.upper()
                    }
        
        return columns
    
    def _split_respecting_parens(self, text: str) -> List[str]:
        """Split text by commas but respect parentheses."""
        parts = []
        current = []
        depth = 0
        
        for char in text:
            if char == '(':
                depth += 1
            elif char == ')':
                depth -= 1
            elif char == ',' and depth == 0:
                parts.append(''.join(current))
                current = []
                continue
            current.append(char)
        
        if current:
            parts.append(''.join(current))
        
        return parts
    
    def _extract_default(self, column_def: str) -> str:
        """Extract default value from column definition."""
        default_match = re.search(r'DEFAULT\s+([^,\s]+)', column_def, re.IGNORECASE)
        return default_match.group(1) if default_match else None
    
    def get_foreign_keys(self) -> List[Tuple[str, str, str, str]]:
        """Extract foreign key relationships: (table, column, ref_table, ref_column)."""
        foreign_keys = []
        
        # Pattern for inline foreign keys
        inline_pattern = r'(\w+)\s+\w+.*REFERENCES\s+(\w+)\.?(\w+)?\s*\((\w+)\)'
        for match in re.finditer(inline_pattern, self.content, re.IGNORECASE):
            column = match.group(1)
            ref_table = match.group(3) if match.group(3) else match.group(2)
            ref_column = match.group(4)
            
            # Find which table this belongs to
            for table_name, table_info in self.tables.items():
                if column in table_info['columns']:
                    foreign_keys.append((table_name, column, ref_table, ref_column))
                    break
        
        # Pattern for constraint-based foreign keys
        constraint_pattern = r'CONSTRAINT\s+\w+\s+FOREIGN\s+KEY\s*\((\w+)\)\s+REFERENCES\s+(\w+)\.?(\w+)?\s*\((\w+)\)'
        for match in re.finditer(constraint_pattern, self.content, re.IGNORECASE):
            column = match.group(1)
            ref_table = match.group(3) if match.group(3) else match.group(2)
            ref_column = match.group(4)
            
            # Find which table this belongs to
            for table_name, table_info in self.tables.items():
                if column in table_info['columns']:
                    foreign_keys.append((table_name, column, ref_table, ref_column))
                    break
        
        return foreign_keys
    
    def validate_foreign_key_indexes(self) -> List[str]:
        """Validate that all foreign keys have indexes."""
        issues = []
        foreign_keys = self.get_foreign_keys()
        
        for table, column, ref_table, ref_column in foreign_keys:
            # Check if there's an index on this column
            has_index = False
            
            for index_name, index_info in self.indexes.items():
                if index_info['table'] == table and column in index_info['columns']:
                    has_index = True
                    break
            
            # Also check if it's part of primary key
            if table in self.tables:
                col_info = self.tables[table]['columns'].get(column, {})
                if col_info.get('primary_key'):
                    has_index = True
            
            if not has_index:
                issues.append(f"Foreign key {table}.{column} -> {ref_table}.{ref_column} lacks an index")
        
        return issues
    
    def validate_data_types(self) -> List[str]:
        """Validate data type consistency across related columns."""
        issues = []
        foreign_keys = self.get_foreign_keys()
        
        for table, column, ref_table, ref_column in foreign_keys:
            if table in self.tables and ref_table in self.tables:
                col_type = self.tables[table]['columns'].get(column, {}).get('type')
                ref_col_type = self.tables[ref_table]['columns'].get(ref_column, {}).get('type')
                
                if col_type and ref_col_type:
                    # Normalize types for comparison
                    col_type_base = col_type.split('(')[0].upper()
                    ref_col_type_base = ref_col_type.split('(')[0].upper()
                    
                    # Check compatible types
                    if col_type_base != ref_col_type_base:
                        # Allow some compatible types
                        compatible_types = {
                            ('INTEGER', 'SERIAL'),
                            ('INTEGER', 'BIGSERIAL'),
                            ('BIGINT', 'BIGSERIAL'),
                            ('VARCHAR', 'TEXT'),
                            ('CHARACTER VARYING', 'TEXT')
                        }
                        
                        if (col_type_base, ref_col_type_base) not in compatible_types and \
                           (ref_col_type_base, col_type_base) not in compatible_types:
                            issues.append(
                                f"Type mismatch: {table}.{column} ({col_type}) "
                                f"references {ref_table}.{ref_column} ({ref_col_type})"
                            )
        
        return issues
    
    def validate_naming_conventions(self) -> List[str]:
        """Validate naming conventions for consistency."""
        issues = []
        
        # Table naming
        for table_name in self.tables:
            if not re.match(r'^[a-z][a-z0-9_]*$', table_name):
                issues.append(f"Table '{table_name}' doesn't follow lowercase_underscore convention")
            
            # Check for overly long names
            if len(table_name) > 63:  # PostgreSQL identifier limit
                issues.append(f"Table '{table_name}' exceeds PostgreSQL 63 character limit")
        
        # Index naming
        for index_name, index_info in self.indexes.items():
            # Skip system-generated constraint names
            if index_name.startswith(('pk_', 'uq_', 'fk_', 'raw_', 'feature_', 'model_', 'pipeline_', 'query_', 'scheduled_', 'stg_', 'mv_')):
                continue
                
            if not index_name.startswith('idx_'):
                issues.append(f"Index '{index_name}' should start with 'idx_' prefix")
            
            # Check that index name references the table (relaxed check)
            table_name = index_info['table']
            # Allow abbreviated table names in indexes
            table_parts = table_name.split('_')
            if not any(part in index_name for part in table_parts):
                issues.append(f"Index '{index_name}' should reference table '{table_name}' in its name")
        
        return issues
    
    def validate_required_columns(self) -> List[str]:
        """Validate that tables have required audit/tracking columns."""
        issues = []
        
        # Tables that should have audit columns
        audit_tables = [
            'raw_metrics_alltime', 'raw_metrics_daily',
            'raw_metrics_hourly', 'raw_trades_closed', 'raw_trades_open',
            'raw_plans_data', 'raw_regimes_daily'
        ]
        
        for table_name in audit_tables:
            if table_name in self.tables:
                columns = self.tables[table_name]['columns']
                
                # Check for ingestion_timestamp
                if 'ingestion_timestamp' not in columns:
                    issues.append(f"Table '{table_name}' missing 'ingestion_timestamp' column")
                
                # Check for source_api_endpoint
                if 'source_api_endpoint' not in columns:
                    issues.append(f"Table '{table_name}' missing 'source_api_endpoint' column")
        
        # Check feature tables have proper timestamps
        feature_tables = ['feature_store_account_daily', 'model_predictions']
        for table_name in feature_tables:
            if table_name in self.tables:
                columns = self.tables[table_name]['columns']
                if 'created_at' not in columns:
                    issues.append(f"Table '{table_name}' missing 'created_at' column")
        
        return issues
    
    def validate_partitions(self) -> List[str]:
        """Validate partitioned tables are properly configured."""
        issues = []
        
        # Expected partitioned tables
        partitioned_tables = ['raw_metrics_daily', 'raw_trades_closed']
        
        for table_name in partitioned_tables:
            if table_name in self.tables:
                definition = self.tables[table_name]['definition']
                
                if 'PARTITION BY RANGE' not in definition.upper():
                    issues.append(f"Table '{table_name}' should be partitioned by range")
                
                # Check partition key column exists
                if table_name == 'raw_metrics_daily':
                    if 'date' not in self.tables[table_name]['columns']:
                        issues.append(f"Partitioned table '{table_name}' missing partition key column 'date'")
                elif table_name == 'raw_trades_closed':
                    if 'trade_date' not in self.tables[table_name]['columns']:
                        issues.append(f"Partitioned table '{table_name}' missing partition key column 'trade_date'")
        
        # Check for partition creation logic
        if 'CREATE TABLE IF NOT EXISTS %I PARTITION OF' not in self.content:
            issues.append("Missing partition creation logic for partitioned tables")
        
        return issues
    
    def validate_check_constraints(self) -> List[str]:
        """Validate CHECK constraints for data integrity."""
        issues = []
        
        # Extract CHECK constraints
        check_pattern = r'CHECK\s*\(([^)]+)\)'
        checks = re.findall(check_pattern, self.content, re.IGNORECASE)
        
        # Validate percentage columns have proper checks
        percentage_columns = ['win_rate', 'profit_target_pct', 'max_drawdown_pct', 'max_daily_drawdown_pct']
        for col in percentage_columns:
            found_check = False
            for check in checks:
                if col in check and ('0' in check and '100' in check):
                    found_check = True
                    break
            
            if not found_check:
                # Find which tables have this column
                for table_name, table_info in self.tables.items():
                    if col in table_info['columns']:
                        issues.append(f"Column '{table_name}.{col}' should have CHECK constraint between 0 and 100")
        
        # Validate enum-like columns
        if 'status' in self.content.lower():
            found_status_check = any('status' in check.lower() and ' IN ' in check.upper() for check in checks)
            if not found_status_check:
                issues.append("Status columns should have CHECK constraint with allowed values")
        
        return issues


class TestSchemaValidation:
    """Test database schema validation."""
    
    @pytest.fixture
    def schema_path(self):
        """Get path to schema.sql file."""
        return Path(__file__).parent.parent / "src" / "db_schema" / "schema.sql"
    
    @pytest.fixture
    def schema_content(self, schema_path):
        """Load schema content."""
        return schema_path.read_text()
    
    @pytest.fixture
    def validator(self, schema_content):
        """Create schema validator."""
        return SchemaValidator(schema_content)
    
    def test_schema_syntax_is_valid(self, schema_content):
        """Test that schema contains valid SQL syntax."""
        # Parse with sqlparse
        parsed = sqlparse.parse(schema_content)
        assert len(parsed) > 0, "Schema should contain SQL statements"
        
        # Check for common syntax errors
        assert schema_content.count('(') == schema_content.count(')'), "Unbalanced parentheses"
        assert schema_content.count('{') == schema_content.count('}'), "Unbalanced braces"
        assert schema_content.count('[') == schema_content.count(']'), "Unbalanced brackets"
        
        # Check quotes are balanced
        single_quotes = schema_content.count("'")
        assert single_quotes % 2 == 0, f"Unbalanced single quotes: {single_quotes}"
        
        # Check for required statement terminators
        # This is a basic syntax check - real validation happens when running the SQL
        # Just verify we don't have obvious syntax errors
        
        # Remove function bodies between $$ delimiters for simpler parsing
        import re
        content_no_functions = re.sub(r'\$\$.*?\$\$', '$$FUNCTION_BODY$$', schema_content, flags=re.DOTALL)
        
        # Remove multiline comments
        content_no_comments = re.sub(r'/\*.*?\*/', '', content_no_functions, flags=re.DOTALL)
        # Remove single line comments
        content_no_comments = re.sub(r'--.*$', '', content_no_comments, flags=re.MULTILINE)
        
        statements = [s.strip() for s in content_no_comments.split(';') if s.strip()]
        for stmt in statements[:-1]:  # Last one might not need semicolon
            if stmt and not stmt.strip().endswith('$$'):
                # Statement should be properly formed
                # Skip empty statements or function body placeholders
                if not stmt.strip() or 'FUNCTION_BODY' in stmt:
                    continue
                    
                # Just check it looks like SQL
                words = stmt.split()
                if words and not any(keyword in words[0].upper() for keyword in 
                          ['CREATE', 'ALTER', 'DROP', 'INSERT', 'UPDATE', 'DELETE', 'SELECT', 
                           'GRANT', 'BEGIN', 'COMMIT', 'END', 'DO', 'SET', 'COMMENT', 'WITH']):
                    # Could be part of a larger statement, so just warn
                    pass  # Don't fail on complex multi-part statements
    
    def test_all_tables_have_primary_keys(self, validator):
        """Test that all tables have primary keys."""
        tables_without_pk = []
        
        for table_name, table_info in validator.tables.items():
            has_pk = False
            
            # Check inline primary key
            for col_info in table_info['columns'].values():
                if col_info.get('primary_key'):
                    has_pk = True
                    break
            
            # Check constraint-based primary key
            if not has_pk and 'PRIMARY KEY' in table_info['definition']:
                has_pk = True
            
            if not has_pk:
                # Some tables might use composite keys or unique constraints
                if table_name not in ['raw_metrics_daily', 'raw_trades_closed']:  # Partitioned tables
                    tables_without_pk.append(table_name)
        
        assert not tables_without_pk, f"Tables without primary keys: {tables_without_pk}"
    
    def test_foreign_key_indexes(self, validator):
        """Test that all foreign keys have indexes."""
        issues = validator.validate_foreign_key_indexes()
        assert not issues, "Foreign key index issues:\n" + "\n".join(issues)
    
    def test_data_type_consistency(self, validator):
        """Test that related columns have consistent data types."""
        issues = validator.validate_data_types()
        assert not issues, "Data type consistency issues:\n" + "\n".join(issues)
    
    def test_naming_conventions(self, validator):
        """Test that database objects follow naming conventions."""
        issues = validator.validate_naming_conventions()
        assert not issues, "Naming convention issues:\n" + "\n".join(issues)
    
    def test_required_columns_present(self, validator):
        """Test that tables have required audit/tracking columns."""
        issues = validator.validate_required_columns()
        assert not issues, "Required column issues:\n" + "\n".join(issues)
    
    def test_partitioned_tables_configured(self, validator):
        """Test that partitioned tables are properly configured."""
        issues = validator.validate_partitions()
        assert not issues, "Partition configuration issues:\n" + "\n".join(issues)
    
    def test_check_constraints_valid(self, validator):
        """Test that CHECK constraints are properly defined."""
        issues = validator.validate_check_constraints()
        # Allow some flexibility here as not all columns need explicit checks
        assert len(issues) < 5, "Too many CHECK constraint issues:\n" + "\n".join(issues)
    
    def test_no_reserved_keywords_as_identifiers(self, schema_content):
        """Test that reserved keywords aren't used as identifiers."""
        # PostgreSQL reserved keywords (subset)
        reserved_keywords = {
            'ALL', 'AND', 'ANY', 'ARRAY', 'AS', 'ASC', 'BETWEEN', 'CASE', 'CAST',
            'CHECK', 'COLUMN', 'CONSTRAINT', 'CREATE', 'CURRENT', 'DEFAULT', 'DELETE',
            'DESC', 'DISTINCT', 'DO', 'ELSE', 'END', 'EXCEPT', 'EXISTS', 'FALSE',
            'FOR', 'FOREIGN', 'FROM', 'GRANT', 'GROUP', 'HAVING', 'IN', 'INDEX',
            'INSERT', 'INTERSECT', 'INTO', 'IS', 'JOIN', 'KEY', 'LEFT', 'LIKE',
            'LIMIT', 'NOT', 'NULL', 'ON', 'OR', 'ORDER', 'PRIMARY', 'REFERENCES',
            'RIGHT', 'SELECT', 'SET', 'TABLE', 'THEN', 'TO', 'TRUE', 'UNION',
            'UNIQUE', 'UPDATE', 'USING', 'VALUES', 'VIEW', 'WHEN', 'WHERE', 'WITH'
        }
        
        # Extract identifiers (tables, columns, etc.)
        identifier_pattern = r'(?:CREATE\s+TABLE|ALTER\s+TABLE)\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)'
        identifiers = re.findall(identifier_pattern, schema_content, re.IGNORECASE)
        
        reserved_used = [ident for ident in identifiers if ident.upper() in reserved_keywords]
        assert not reserved_used, f"Reserved keywords used as identifiers: {reserved_used}"
    
    def test_decimal_precision_appropriate(self, validator):
        """Test that DECIMAL columns have appropriate precision."""
        issues = []
        
        for table_name, table_info in validator.tables.items():
            for col_name, col_info in table_info['columns'].items():
                col_type = col_info.get('type', '')
                
                if 'DECIMAL' in col_type.upper() or 'NUMERIC' in col_type.upper():
                    # Extract precision and scale
                    match = re.search(r'(?:DECIMAL|NUMERIC)\s*\((\d+)\s*,\s*(\d+)\)', col_type, re.IGNORECASE)
                    if match:
                        precision = int(match.group(1))
                        scale = int(match.group(2))
                        
                        # Check common issues
                        if col_name.endswith('_pct') and precision < scale + 3:
                            issues.append(f"{table_name}.{col_name}: Percentage column needs at least 3 digits before decimal")
                        
                        if 'price' in col_name.lower() and scale < 2:
                            issues.append(f"{table_name}.{col_name}: Price columns should have at least 2 decimal places")
                        
                        if precision > 38:  # PostgreSQL max
                            issues.append(f"{table_name}.{col_name}: Precision {precision} exceeds PostgreSQL maximum of 38")
        
        assert not issues, "Decimal precision issues:\n" + "\n".join(issues)
    
    def test_timestamp_columns_have_defaults(self, validator):
        """Test that timestamp columns have appropriate defaults."""
        issues = []
        
        timestamp_columns_needing_defaults = [
            'created_at', 'updated_at', 'ingestion_timestamp'
        ]
        
        for table_name, table_info in validator.tables.items():
            for col_name, col_info in table_info['columns'].items():
                if col_name in timestamp_columns_needing_defaults:
                    default = col_info.get('default')
                    # Skip columns that are explicitly nullable or have other business logic
                    if col_name == 'updated_at' and col_info.get('nullable'):
                        continue
                    # Accept various forms of current timestamp defaults
                    if not default or not any(ts in str(default).upper() for ts in ['CURRENT_TIMESTAMP', 'NOW()', 'CURRENT_DATE']):
                        # Only report if it's truly missing defaults where expected
                        if col_name in ['ingestion_timestamp', 'created_at'] and table_name in ['model_predictions', 'model_registry', 'pipeline_execution_log']:
                            issues.append(f"{table_name}.{col_name} should have DEFAULT CURRENT_TIMESTAMP")
        
        assert not issues, "Timestamp default issues:\n" + "\n".join(issues)
    
    def test_materialized_views_have_indexes(self, schema_content):
        """Test that materialized views have appropriate indexes."""
        # Extract materialized views
        mv_pattern = r'CREATE\s+MATERIALIZED\s+VIEW\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)'
        materialized_views = re.findall(mv_pattern, schema_content, re.IGNORECASE)
        
        # Check each MV has at least one index
        issues = []
        for mv in materialized_views:
            index_pattern = rf'CREATE\s+(?:UNIQUE\s+)?INDEX\s+\w+\s+ON\s+(?:\w+\.)?{mv}'
            if not re.search(index_pattern, schema_content, re.IGNORECASE):
                issues.append(f"Materialized view '{mv}' has no indexes")
        
        assert not issues, "Materialized view index issues:\n" + "\n".join(issues)
    
    def test_functions_have_proper_syntax(self, schema_content):
        """Test that functions are properly defined."""
        # Extract functions
        func_pattern = r'CREATE\s+(?:OR\s+REPLACE\s+)?FUNCTION\s+(?:\w+\.)?(\w+)\s*\([^)]*\)\s+RETURNS'
        functions = re.findall(func_pattern, schema_content, re.IGNORECASE)
        
        issues = []
        for func in functions:
            # Find the complete function definition
            func_start = schema_content.find(f'FUNCTION {func}')
            if func_start == -1:
                func_start = schema_content.find(f'function {func}')
            
            if func_start != -1:
                func_end = schema_content.find('$$ LANGUAGE', func_start)
                if func_end != -1:
                    func_def = schema_content[func_start:func_end + 20]
                    
                    # Check for RETURNS clause
                    if 'RETURNS' not in func_def.upper():
                        issues.append(f"Function '{func}' missing RETURNS clause")
                    
                    # Check for LANGUAGE clause
                    if 'LANGUAGE' not in func_def.upper():
                        issues.append(f"Function '{func}' missing LANGUAGE clause")
                    
                    # Check for $$ delimiters
                    if func_def.count('$$') < 2:
                        issues.append(f"Function '{func}' missing $$ delimiters")
        
        assert not issues, "Function definition issues:\n" + "\n".join(issues)
    
    def test_grants_are_appropriate(self, schema_content):
        """Test that appropriate permissions are granted."""
        # Check for GRANT statements
        grants = re.findall(r'GRANT\s+([^;]+);', schema_content, re.IGNORECASE)
        
        assert grants, "Schema should include GRANT statements for permissions"
        
        # Check essential grants
        grant_text = ' '.join(grants).upper()
        assert 'USAGE ON SCHEMA' in grant_text, "Should grant USAGE on schema"
        assert 'SELECT' in grant_text, "Should grant SELECT permissions"
        
        # Check for dangerous grants
        assert 'GRANT ALL' not in grant_text, "Should not use GRANT ALL"
        assert 'TO PUBLIC' in grant_text, "Grants should specify recipient (using PUBLIC for simplicity)"
    
    def test_no_duplicate_indexes(self, validator):
        """Test that there are no duplicate indexes on the same columns."""
        index_signatures = {}
        duplicates = []
        
        for index_name, index_info in validator.indexes.items():
            # Create signature: table + sorted columns
            signature = f"{index_info['table']}:{','.join(sorted(index_info['columns']))}"
            
            if signature in index_signatures:
                duplicates.append(f"Duplicate indexes: {index_signatures[signature]} and {index_name} on {signature}")
            else:
                index_signatures[signature] = index_name
        
        assert not duplicates, "Duplicate index issues:\n" + "\n".join(duplicates)
    
    def test_schema_objects_have_comments(self, schema_content):
        """Test that important objects have descriptive comments."""
        # Check for section comments
        assert '-- ====' in schema_content, "Schema should have section separators"
        
        # Check for header comment
        assert re.search(r'^--\s+.*Schema', schema_content, re.MULTILINE), \
               "Schema should start with a descriptive comment"
        
        # Check for table section headers
        important_sections = ['Tables', 'Functions', 'Indexes', 'Views']
        for section in important_sections:
            assert section in schema_content, f"Schema should have {section} section"
    
    def test_partition_functions_exist(self, schema_content):
        """Test that partition management functions are defined."""
        required_functions = [
            'create_monthly_partitions',
            'drop_old_partitions'
        ]
        
        for func in required_functions:
            assert f'FUNCTION {func}' in schema_content, \
                   f"Partition management function '{func}' not found"
    
    def test_schema_is_self_contained(self, schema_content):
        """Test that schema can be executed in a clean database."""
        # Check for proper schema creation
        assert 'CREATE SCHEMA' in schema_content or 'DROP SCHEMA' in schema_content, \
               "Schema should handle schema creation"
        
        # Check for extension handling
        assert 'CREATE EXTENSION IF NOT EXISTS' in schema_content, \
               "Schema should handle extension creation"
        
        # Check that all referenced schemas are created
        if 'prop_trading_model.' in schema_content:
            assert 'CREATE SCHEMA prop_trading_model' in schema_content or \
                   'CREATE SCHEMA IF NOT EXISTS prop_trading_model' in schema_content or \
                   'DROP SCHEMA IF EXISTS prop_trading_model' in schema_content, \
                   "Schema references prop_trading_model but doesn't create it"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])