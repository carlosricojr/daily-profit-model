#!/usr/bin/env python3
"""
Generate SQLAlchemy models from the database schema.
Only generates models for parent tables, not partitions.
"""
import os
import subprocess
import sys
from typing import List

# Try to load dotenv if available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # If python-dotenv not installed, environment variables should already be set
    pass


def get_non_partition_tables() -> List[str]:
    """Get list of tables that are not partitions."""
    # These are the core tables in prop_trading_model schema
    # Excludes partition tables (ending with _YYYY_MM) and backup tables (_old)
    return [
        # Feature store
        "feature_store_account_daily",
        
        # Model tables
        "model_predictions",
        "model_registry",
        "model_training_input",
        
        # Pipeline and logging
        "pipeline_execution_log",
        "query_performance_log",
        
        # Raw data tables (parent tables for partitions)
        "raw_metrics_alltime",
        "raw_metrics_daily",
        "raw_metrics_hourly",
        "raw_plans_data",
        "raw_regimes_daily",
        "raw_trades_closed",
        "raw_trades_open",
        
        # System tables
        "schema_migrations",
        "schema_version",
       
    ]


def generate_models(output_file: str = "src/db_schema/models.py") -> bool:
    """Generate SQLAlchemy models from database."""
    # Get database URL
    db_url = os.getenv('DB_CONNECTION_STRING_SESSION_POOLER')
    if not db_url:
        print("❌ Error: DB_CONNECTION_STRING_SESSION_POOLER not set")
        return False
    
    # Get tables to generate
    tables = get_non_partition_tables()
    
    # Build command
    cmd = [
        "sqlacodegen",
        db_url,
        "--schemas", "prop_trading_model",
        "--generator", "declarative",
        "--tables", ",".join(tables),
        "--outfile", output_file
    ]
    
    print("🔄 Generating SQLAlchemy models from database...")
    print(f"   Tables: {len(tables)} core tables")
    print(f"   Output: {output_file}")
    
    # Run sqlacodegen
    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True)
        print("✅ Models generated successfully!")
        print(f"   File: {output_file}")
        
        # Show summary
        with open(output_file, 'r') as f:
            content = f.read()
            class_count = content.count('class ')
            print(f"   Classes: {class_count} model classes generated")
            
        return True
        
    except subprocess.CalledProcessError as e:
        print("❌ Error generating models:")
        print(f"   {e.stderr}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False


def verify_models(model_file: str = "src/db_schema/models.py") -> bool:
    """Verify the generated models can be imported."""
    print("\n🔍 Verifying generated models...")
    
    try:
        # Add src to path
        sys.path.insert(0, 'src')
        
        # Try to import the models
        from db_schema import models
        
        # Count the model classes
        model_classes = [
            name for name in dir(models) 
            if name[0].isupper() and hasattr(getattr(models, name), '__tablename__')
        ]
        
        print("✅ Models verified!")
        print(f"   Importable classes: {len(model_classes)}")
        print(f"   Examples: {', '.join(model_classes[:5])}...")
        
        return True
        
    except Exception as e:
        print(f"❌ Error verifying models: {e}")
        return False


def main():
    """Main function."""
    print("="*60)
    print("SQLAlchemy Model Generator")
    print("="*60)
    
    # Generate models
    success = generate_models()
    
    if success:
        # Verify they work
        verify_models()
        
        print("\n📝 Notes:")
        print("   - Only parent tables are included (not partitions)")
        print("   - Partition tables inherit structure from parents")
        print("   - Use parent table models for all queries")
        print("   - PostgreSQL handles partition routing automatically")
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())