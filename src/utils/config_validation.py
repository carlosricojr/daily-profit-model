"""
Configuration validation utilities.
Validates environment variables and configuration settings.
"""

import os
from typing import Dict, Any, List, Optional, Union, Callable
from dataclasses import dataclass
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
    validator: Optional[Callable] = None
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