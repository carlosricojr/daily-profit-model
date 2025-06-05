"""
Version 1: Conservative - Configuration validation utilities.
Validates environment variables and configuration settings.
"""

import os
from typing import Dict, Any, List, Optional, Union
from dataclasses import dataclass, field
import json

from .logging_config import get_logger


logger = get_logger(__name__)


@dataclass
class ConfigField:
    """Represents a configuration field with validation rules."""
    name: str
    required: bool = True
    default: Any = None
    type: type = str
    validator: Optional[callable] = None
    description: str = ""
    choices: Optional[List[Any]] = None
    min_value: Optional[Union[int, float]] = None
    max_value: Optional[Union[int, float]] = None


class ConfigurationError(Exception):
    """Configuration validation error."""
    pass


class ConfigValidator:
    """Validates configuration from environment variables."""
    
    def __init__(self):
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.config: Dict[str, Any] = {}
    
    def validate_field(self, field: ConfigField) -> Any:
        """
        Validate a single configuration field.
        
        Args:
            field: ConfigField definition
            
        Returns:
            Validated value
            
        Raises:
            ConfigurationError: If validation fails
        """
        # Get value from environment
        raw_value = os.getenv(field.name)
        
        # Check if required
        if raw_value is None:
            if field.required:
                self.errors.append(f"Required configuration '{field.name}' is missing")
                return None
            else:
                return field.default
        
        # Type conversion
        try:
            if field.type == bool:
                value = raw_value.lower() in ('true', '1', 'yes', 'on')
            elif field.type == int:
                value = int(raw_value)
            elif field.type == float:
                value = float(raw_value)
            elif field.type == list:
                value = [item.strip() for item in raw_value.split(',')]
            elif field.type == dict:
                value = json.loads(raw_value)
            else:
                value = raw_value
        except (ValueError, json.JSONDecodeError) as e:
            self.errors.append(
                f"Invalid type for '{field.name}': expected {field.type.__name__}, "
                f"got '{raw_value}' - {str(e)}"
            )
            return None
        
        # Validate choices
        if field.choices and value not in field.choices:
            self.errors.append(
                f"Invalid value for '{field.name}': '{value}' not in {field.choices}"
            )
            return None
        
        # Validate numeric ranges
        if field.min_value is not None and value < field.min_value:
            self.errors.append(
                f"Value for '{field.name}' ({value}) is below minimum ({field.min_value})"
            )
            return None
        
        if field.max_value is not None and value > field.max_value:
            self.errors.append(
                f"Value for '{field.name}' ({value}) is above maximum ({field.max_value})"
            )
            return None
        
        # Custom validation
        if field.validator:
            try:
                if not field.validator(value):
                    self.errors.append(
                        f"Custom validation failed for '{field.name}' with value '{value}'"
                    )
                    return None
            except Exception as e:
                self.errors.append(
                    f"Validator error for '{field.name}': {str(e)}"
                )
                return None
        
        return value
    
    def validate_all(self, fields: List[ConfigField]) -> Dict[str, Any]:
        """
        Validate all configuration fields.
        
        Args:
            fields: List of ConfigField definitions
            
        Returns:
            Dictionary of validated configuration values
            
        Raises:
            ConfigurationError: If any required validation fails
        """
        self.errors.clear()
        self.warnings.clear()
        self.config.clear()
        
        for field in fields:
            value = self.validate_field(field)
            if value is not None or not field.required:
                self.config[field.name] = value
        
        # Log validation results
        if self.errors:
            logger.error(
                "Configuration validation failed",
                extra={'extra_fields': {
                    'errors': self.errors,
                    'error_count': len(self.errors)
                }}
            )
            raise ConfigurationError(
                f"Configuration validation failed with {len(self.errors)} errors:\n" +
                "\n".join(f"  - {error}" for error in self.errors)
            )
        
        if self.warnings:
            logger.warning(
                "Configuration validation warnings",
                extra={'extra_fields': {
                    'warnings': self.warnings,
                    'warning_count': len(self.warnings)
                }}
            )
        
        logger.info(
            "Configuration validated successfully",
            extra={'extra_fields': {
                'config_keys': list(self.config.keys()),
                'field_count': len(fields)
            }}
        )
        
        return self.config


# Database configuration fields
DATABASE_CONFIG_FIELDS = [
    ConfigField(
        name="DB_HOST",
        required=True,
        type=str,
        description="Database host"
    ),
    ConfigField(
        name="DB_PORT",
        required=False,
        default=5432,
        type=int,
        min_value=1,
        max_value=65535,
        description="Database port"
    ),
    ConfigField(
        name="DB_NAME",
        required=True,
        type=str,
        description="Database name"
    ),
    ConfigField(
        name="DB_USER",
        required=True,
        type=str,
        description="Database user"
    ),
    ConfigField(
        name="DB_PASSWORD",
        required=True,
        type=str,
        description="Database password"
    ),
    ConfigField(
        name="DB_CONNECTION_TIMEOUT",
        required=False,
        default=30,
        type=int,
        min_value=1,
        max_value=300,
        description="Database connection timeout in seconds"
    ),
    ConfigField(
        name="DB_QUERY_TIMEOUT",
        required=False,
        default=300,
        type=int,
        min_value=1,
        max_value=3600,
        description="Database query timeout in seconds"
    ),
    ConfigField(
        name="DB_MAX_RETRIES",
        required=False,
        default=3,
        type=int,
        min_value=0,
        max_value=10,
        description="Maximum number of database retry attempts"
    ),
    ConfigField(
        name="DB_POOL_MIN_SIZE",
        required=False,
        default=1,
        type=int,
        min_value=1,
        max_value=10,
        description="Minimum database connection pool size"
    ),
    ConfigField(
        name="DB_POOL_MAX_SIZE",
        required=False,
        default=10,
        type=int,
        min_value=1,
        max_value=100,
        description="Maximum database connection pool size"
    ),
]

# API configuration fields
API_CONFIG_FIELDS = [
    ConfigField(
        name="API_KEY",
        required=True,
        type=str,
        description="API key for authentication"
    ),
    ConfigField(
        name="API_BASE_URL",
        required=False,
        default="https://easton.apis.arizet.io/risk-analytics/tft/external/",
        type=str,
        validator=lambda x: x.startswith(('http://', 'https://')),
        description="Base URL for the API"
    ),
    ConfigField(
        name="API_REQUESTS_PER_SECOND",
        required=False,
        default=10,
        type=int,
        min_value=1,
        max_value=100,
        description="API rate limit (requests per second)"
    ),
    ConfigField(
        name="API_MAX_RETRIES",
        required=False,
        default=3,
        type=int,
        min_value=0,
        max_value=10,
        description="Maximum number of API retry attempts"
    ),
    ConfigField(
        name="API_TIMEOUT",
        required=False,
        default=30,
        type=int,
        min_value=1,
        max_value=300,
        description="API request timeout in seconds"
    ),
    ConfigField(
        name="API_VERIFY_SSL",
        required=False,
        default=True,
        type=bool,
        description="Whether to verify SSL certificates"
    ),
]

# Logging configuration fields
LOGGING_CONFIG_FIELDS = [
    ConfigField(
        name="LOG_LEVEL",
        required=False,
        default="INFO",
        type=str,
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        description="Logging level"
    ),
    ConfigField(
        name="LOG_DIR",
        required=False,
        default="logs",
        type=str,
        description="Directory for log files"
    ),
    ConfigField(
        name="LOG_FORMAT",
        required=False,
        default="json",
        type=str,
        choices=["json", "text"],
        description="Log format (json or text)"
    ),
    ConfigField(
        name="LOG_MAX_BYTES",
        required=False,
        default=10485760,  # 10MB
        type=int,
        min_value=1048576,  # 1MB
        max_value=104857600,  # 100MB
        description="Maximum log file size in bytes"
    ),
    ConfigField(
        name="LOG_BACKUP_COUNT",
        required=False,
        default=5,
        type=int,
        min_value=0,
        max_value=100,
        description="Number of log backup files to keep"
    ),
]


def validate_all_config() -> Dict[str, Any]:
    """
    Validate all configuration settings.
    
    Returns:
        Dictionary with all validated configuration
        
    Raises:
        ConfigurationError: If validation fails
    """
    validator = ConfigValidator()
    
    all_fields = DATABASE_CONFIG_FIELDS + API_CONFIG_FIELDS + LOGGING_CONFIG_FIELDS
    config = validator.validate_all(all_fields)
    
    # Group configuration by category
    grouped_config = {
        'database': {k: v for k, v in config.items() if k.startswith('DB_')},
        'api': {k: v for k, v in config.items() if k.startswith('API_')},
        'logging': {k: v for k, v in config.items() if k.startswith('LOG_')}
    }
    
    return grouped_config


def print_config_template():
    """Print a template .env file with all configuration options."""
    all_fields = DATABASE_CONFIG_FIELDS + API_CONFIG_FIELDS + LOGGING_CONFIG_FIELDS
    
    print("# Daily Profit Model Configuration Template")
    print("# Copy this to .env and fill in the values\n")
    
    current_category = None
    
    for field in all_fields:
        # Determine category
        if field.name.startswith('DB_'):
            category = "Database Configuration"
        elif field.name.startswith('API_'):
            category = "API Configuration"
        elif field.name.startswith('LOG_'):
            category = "Logging Configuration"
        else:
            category = "Other Configuration"
        
        # Print category header if changed
        if category != current_category:
            print(f"\n# {category}")
            current_category = category
        
        # Print field description
        print(f"# {field.description}")
        if field.choices:
            print(f"# Choices: {', '.join(map(str, field.choices))}")
        if field.min_value is not None or field.max_value is not None:
            range_str = f"# Range: "
            if field.min_value is not None:
                range_str += f"{field.min_value} <= value"
            if field.max_value is not None:
                if field.min_value is not None:
                    range_str += f" <= {field.max_value}"
                else:
                    range_str += f"value <= {field.max_value}"
            print(range_str)
        
        # Print field with default value
        if field.required:
            print(f"{field.name}=")
        else:
            print(f"# {field.name}={field.default}")
        print()


if __name__ == "__main__":
    # If run directly, print configuration template
    print_config_template()