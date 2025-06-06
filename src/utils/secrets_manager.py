"""
Version 2: Balanced - Basic secrets management.
Implements secure secret storage and retrieval with encryption.
"""

import os
import json
import base64
from typing import Dict, Optional, List
from pathlib import Path
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import keyring
from datetime import datetime
import threading

from .logging_config import get_logger


logger = get_logger(__name__)


class SecretsManager:
    """Basic secrets management with encryption."""

    def __init__(
        self,
        secrets_file: Optional[str] = None,
        use_keyring: bool = True,
        cache_ttl: int = 300,
    ):
        """
        Initialize secrets manager.

        Args:
            secrets_file: Path to encrypted secrets file
            use_keyring: Whether to use system keyring
            cache_ttl: Cache TTL in seconds
        """
        self.secrets_file = secrets_file or os.getenv(
            "SECRETS_FILE", os.path.expanduser("~/.daily-profit-model/secrets.enc")
        )
        self.use_keyring = use_keyring
        self.cache_ttl = cache_ttl

        # Initialize encryption
        self._cipher = None
        self._master_key = None

        # Secret cache
        self._cache = {}
        self._cache_timestamps = {}
        self._lock = threading.Lock()

        # Service name for keyring
        self.service_name = "daily-profit-model"

        # Initialize
        self._initialize_encryption()

        logger.info(
            "Secrets manager initialized",
            extra={
                "extra_fields": {
                    "use_keyring": use_keyring,
                    "secrets_file": self.secrets_file,
                }
            },
        )

    def _initialize_encryption(self):
        """Initialize encryption key."""
        # Try to get master key from environment
        master_key = os.getenv("SECRETS_MASTER_KEY")

        if not master_key and self.use_keyring:
            # Try to get from system keyring
            try:
                master_key = keyring.get_password(self.service_name, "master_key")
            except Exception as e:
                logger.warning(f"Failed to get master key from keyring: {str(e)}")

        if not master_key:
            # Generate new master key
            master_key = Fernet.generate_key().decode()

            if self.use_keyring:
                # Store in keyring
                try:
                    keyring.set_password(self.service_name, "master_key", master_key)
                    logger.info("Generated and stored new master key in keyring")
                except Exception as e:
                    logger.warning(f"Failed to store master key in keyring: {str(e)}")

            # Also log it for manual storage
            logger.warning(
                "Generated new master key. Store this securely: "
                f"export SECRETS_MASTER_KEY='{master_key}'"
            )

        # Create cipher
        self._master_key = master_key.encode()
        self._cipher = Fernet(self._master_key)

    def _derive_key(self, password: str, salt: bytes) -> bytes:
        """Derive encryption key from password."""
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        return key

    def set_secret(self, name: str, value: str, namespace: Optional[str] = None):
        """
        Set a secret value.

        Args:
            name: Secret name
            value: Secret value
            namespace: Optional namespace for grouping
        """
        key = f"{namespace}:{name}" if namespace else name

        with self._lock:
            # Update cache
            self._cache[key] = value
            self._cache_timestamps[key] = datetime.now()

            # Use keyring if available
            if self.use_keyring:
                try:
                    keyring.set_password(self.service_name, key, value)
                    logger.info(f"Stored secret '{key}' in keyring")
                    return
                except Exception as e:
                    logger.warning(f"Failed to store in keyring: {str(e)}")

            # Fall back to encrypted file
            self._save_to_file()

    def get_secret(self, name: str, namespace: Optional[str] = None) -> Optional[str]:
        """
        Get a secret value.

        Args:
            name: Secret name
            namespace: Optional namespace

        Returns:
            Secret value or None if not found
        """
        key = f"{namespace}:{name}" if namespace else name

        with self._lock:
            # Check cache
            if key in self._cache:
                timestamp = self._cache_timestamps.get(key)
                if timestamp and (datetime.now() - timestamp).seconds < self.cache_ttl:
                    return self._cache[key]

            # Try keyring
            if self.use_keyring:
                try:
                    value = keyring.get_password(self.service_name, key)
                    if value:
                        self._cache[key] = value
                        self._cache_timestamps[key] = datetime.now()
                        return value
                except Exception as e:
                    logger.warning(f"Failed to get from keyring: {str(e)}")

            # Try encrypted file
            secrets = self._load_from_file()
            if secrets and key in secrets:
                value = secrets[key]
                self._cache[key] = value
                self._cache_timestamps[key] = datetime.now()
                return value

            # Try environment variable as fallback
            env_key = key.upper().replace(":", "_").replace("-", "_")
            value = os.getenv(env_key)
            if value:
                logger.info(f"Found secret '{key}' in environment variable {env_key}")
                # Cache it
                self._cache[key] = value
                self._cache_timestamps[key] = datetime.now()
                return value

            return None

    def delete_secret(self, name: str, namespace: Optional[str] = None):
        """Delete a secret."""
        key = f"{namespace}:{name}" if namespace else name

        with self._lock:
            # Remove from cache
            self._cache.pop(key, None)
            self._cache_timestamps.pop(key, None)

            # Remove from keyring
            if self.use_keyring:
                try:
                    keyring.delete_password(self.service_name, key)
                    logger.info(f"Deleted secret '{key}' from keyring")
                except Exception as e:
                    logger.warning(f"Failed to delete from keyring: {str(e)}")

            # Remove from file
            secrets = self._load_from_file()
            if secrets and key in secrets:
                del secrets[key]
                self._save_to_file(secrets)

    def list_secrets(self, namespace: Optional[str] = None) -> List[str]:
        """List all secret names."""
        secrets = set()

        # From cache
        with self._lock:
            for key in self._cache.keys():
                if namespace:
                    if key.startswith(f"{namespace}:"):
                        secrets.add(key)
                else:
                    secrets.add(key)

        # From file
        file_secrets = self._load_from_file()
        if file_secrets:
            for key in file_secrets.keys():
                if namespace:
                    if key.startswith(f"{namespace}:"):
                        secrets.add(key)
                else:
                    secrets.add(key)

        return sorted(list(secrets))

    def _save_to_file(self, secrets: Optional[Dict[str, str]] = None):
        """Save secrets to encrypted file."""
        if secrets is None:
            secrets = self._cache.copy()

        try:
            # Create directory if needed
            Path(self.secrets_file).parent.mkdir(parents=True, exist_ok=True)

            # Encrypt and save
            data = json.dumps(secrets).encode()
            encrypted = self._cipher.encrypt(data)

            with open(self.secrets_file, "wb") as f:
                f.write(encrypted)

            # Set restrictive permissions
            os.chmod(self.secrets_file, 0o600)

            logger.debug(f"Saved {len(secrets)} secrets to encrypted file")

        except Exception as e:
            logger.error(f"Failed to save secrets to file: {str(e)}")

    def _load_from_file(self) -> Optional[Dict[str, str]]:
        """Load secrets from encrypted file."""
        if not os.path.exists(self.secrets_file):
            return None

        try:
            with open(self.secrets_file, "rb") as f:
                encrypted = f.read()

            decrypted = self._cipher.decrypt(encrypted)
            secrets = json.loads(decrypted.decode())

            logger.debug(f"Loaded {len(secrets)} secrets from encrypted file")
            return secrets

        except Exception as e:
            logger.error(f"Failed to load secrets from file: {str(e)}")
            return None

    def rotate_master_key(self, new_key: Optional[str] = None) -> str:
        """
        Rotate the master encryption key.

        Args:
            new_key: New master key (generated if not provided)

        Returns:
            New master key
        """
        if not new_key:
            new_key = Fernet.generate_key().decode()

        # Load all secrets with old key
        all_secrets = {}

        # From cache
        with self._lock:
            all_secrets.update(self._cache)

        # From file
        file_secrets = self._load_from_file()
        if file_secrets:
            all_secrets.update(file_secrets)

        # Update cipher with new key
        self._master_key = new_key.encode()
        self._cipher = Fernet(self._master_key)

        # Re-encrypt and save all secrets
        self._save_to_file(all_secrets)

        # Update keyring if used
        if self.use_keyring:
            try:
                keyring.set_password(self.service_name, "master_key", new_key)
                logger.info("Updated master key in keyring")
            except Exception as e:
                logger.warning(f"Failed to update master key in keyring: {str(e)}")

        logger.info("Master key rotated successfully")
        return new_key

    def clear_cache(self):
        """Clear the secret cache."""
        with self._lock:
            self._cache.clear()
            self._cache_timestamps.clear()

        logger.info("Secret cache cleared")


class SecretProvider:
    """Interface for different secret providers."""

    def get(self, key: str) -> Optional[str]:
        """Get a secret value."""
        raise NotImplementedError

    def set(self, key: str, value: str):
        """Set a secret value."""
        raise NotImplementedError

    def delete(self, key: str):
        """Delete a secret."""
        raise NotImplementedError


class EnvironmentSecretProvider(SecretProvider):
    """Secret provider using environment variables."""

    def __init__(self, prefix: str = "DPM_"):
        self.prefix = prefix

    def get(self, key: str) -> Optional[str]:
        env_key = f"{self.prefix}{key.upper()}"
        return os.getenv(env_key)

    def set(self, key: str, value: str):
        env_key = f"{self.prefix}{key.upper()}"
        os.environ[env_key] = value

    def delete(self, key: str):
        env_key = f"{self.prefix}{key.upper()}"
        os.environ.pop(env_key, None)


class FileSecretProvider(SecretProvider):
    """Secret provider using encrypted files."""

    def __init__(self, secrets_manager: SecretsManager):
        self.secrets_manager = secrets_manager

    def get(self, key: str) -> Optional[str]:
        return self.secrets_manager.get_secret(key)

    def set(self, key: str, value: str):
        self.secrets_manager.set_secret(key, value)

    def delete(self, key: str):
        self.secrets_manager.delete_secret(key)


class ChainedSecretProvider(SecretProvider):
    """Chain multiple secret providers with fallback."""

    def __init__(self, providers: List[SecretProvider]):
        self.providers = providers

    def get(self, key: str) -> Optional[str]:
        for provider in self.providers:
            value = provider.get(key)
            if value is not None:
                return value
        return None

    def set(self, key: str, value: str):
        # Set in the first provider
        if self.providers:
            self.providers[0].set(key, value)

    def delete(self, key: str):
        # Delete from all providers
        for provider in self.providers:
            try:
                provider.delete(key)
            except Exception:
                pass


# Global secrets manager instance
_secrets_manager = None


def get_secrets_manager() -> SecretsManager:
    """Get the global secrets manager instance."""
    global _secrets_manager
    if _secrets_manager is None:
        _secrets_manager = SecretsManager()
    return _secrets_manager


def get_secret(name: str, namespace: Optional[str] = None) -> Optional[str]:
    """Convenience function to get a secret."""
    return get_secrets_manager().get_secret(name, namespace)


def set_secret(name: str, value: str, namespace: Optional[str] = None):
    """Convenience function to set a secret."""
    get_secrets_manager().set_secret(name, value, namespace)
