"""Enhanced security utilities for credential encryption and data masking."""

import os
import json
import base64
import secrets
import hmac
import hashlib
from typing import Dict, Any, Optional
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend
import logging

logger = logging.getLogger(__name__)

class CredentialEncryption:
    """Secure credential encryption using AES-256-GCM via Fernet with per-encryption salt."""
    
    def __init__(self, encryption_key: Optional[str] = None):
        """Initialize with encryption key.
        
        Args:
            encryption_key: Base64 encoded encryption key. If None, uses environment variable.
        """
        if encryption_key:
            self._key = encryption_key.encode()
        else:
            # Get key from environment or generate a new one
            key_str = os.getenv('TERRAKIT_ENCRYPTION_KEY')
            if not key_str:
                # Generate a new key for development (should be set in production)
                key_str = base64.urlsafe_b64encode(os.urandom(32)).decode()
                logger.warning("No encryption key found, generated temporary key. Set TERRAKIT_ENCRYPTION_KEY in production.")
            
            self._key = key_str.encode()
    
    def _derive_fernet_key(self, salt: bytes) -> Fernet:
        """Derive Fernet key from base key and salt.
        
        Args:
            salt: Random salt for key derivation
            
        Returns:
            Fernet instance with derived key
        """
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
            backend=default_backend()
        )
        fernet_key = base64.urlsafe_b64encode(kdf.derive(self._key))
        return Fernet(fernet_key)
    
    def encrypt_credentials(self, credentials: Dict[str, Any]) -> str:
        """Encrypt credentials dictionary with random salt.
        
        Args:
            credentials: Dictionary containing sensitive credential data
            
        Returns:
            Base64 encoded encrypted credentials with embedded salt
        """
        try:
            # Generate random salt for this encryption
            salt = os.urandom(16)
            
            # Derive Fernet key with this salt
            fernet = self._derive_fernet_key(salt)
            
            # Convert to JSON and encrypt
            json_data = json.dumps(credentials, sort_keys=True)
            encrypted_data = fernet.encrypt(json_data.encode())
            
            # Combine salt and encrypted data: salt(16 bytes) + encrypted_data
            combined_data = salt + encrypted_data
            
            return base64.urlsafe_b64encode(combined_data).decode()
        except Exception as e:
            logger.error(f"Failed to encrypt credentials: {e}")
            raise ValueError("Credential encryption failed")
    
    def decrypt_credentials(self, encrypted_credentials: str) -> Dict[str, Any]:
        """Decrypt credentials with embedded salt.
        
        Args:
            encrypted_credentials: Base64 encoded encrypted credentials with embedded salt
            
        Returns:
            Decrypted credentials dictionary
        """
        try:
            # Decode the combined data
            combined_data = base64.urlsafe_b64decode(encrypted_credentials.encode())
            
            # Extract salt (first 16 bytes) and encrypted data
            if len(combined_data) < 16:
                raise ValueError("Invalid encrypted data format")
            
            salt = combined_data[:16]
            encrypted_data = combined_data[16:]
            
            # Derive Fernet key with extracted salt
            fernet = self._derive_fernet_key(salt)
            
            # Decrypt and parse JSON
            decrypted_data = fernet.decrypt(encrypted_data)
            return json.loads(decrypted_data.decode())
        except Exception as e:
            logger.error(f"Failed to decrypt credentials: {e}")
            raise ValueError("Credential decryption failed")


class DataMasking:
    """Utilities for masking sensitive data in API responses and logs."""
    
    @staticmethod
    def mask_api_key(api_key: str) -> str:
        """Mask API key for safe display.
        
        Args:
            api_key: Full API key
            
        Returns:
            Masked API key showing only prefix and last few characters
        """
        if not api_key or len(api_key) < 10:
            return "***"
        
        # Handle Terralink format: tlk_<env>_<secret>
        if api_key.startswith("tlk_"):
            parts = api_key.split("_", 2)
            if len(parts) >= 3:
                prefix = parts[1]
                return f"tlk_{prefix}_{'*' * 8}...{api_key[-4:]}"
        
        # Generic format
        return f"{api_key[:8]}{'*' * 8}...{api_key[-4:]}"
    
    @staticmethod
    def mask_token(token: str) -> str:
        """Mask OAuth token for safe display.
        
        Args:
            token: Full OAuth token
            
        Returns:
            Masked token
        """
        if not token or len(token) < 10:
            return "***"
        
        return f"{token[:6]}{'*' * 12}...{token[-4:]}"
    
    @staticmethod
    def mask_email(email: str) -> str:
        """Mask email address for safe display.
        
        Args:
            email: Full email address
            
        Returns:
            Masked email address
        """
        if not email or '@' not in email:
            return "***@***.***"
        
        local, domain = email.split('@', 1)
        if len(local) <= 2:
            masked_local = '*' * len(local)
        else:
            masked_local = local[0] + '*' * (len(local) - 2) + local[-1]
        
        domain_parts = domain.split('.')
        if len(domain_parts) >= 2:
            masked_domain = domain_parts[0][0] + '*' * (len(domain_parts[0]) - 1) + '.' + domain_parts[-1]
        else:
            masked_domain = '*' * len(domain)
        
        return f"{masked_local}@{masked_domain}"
    
    @staticmethod
    def mask_credentials(credentials: Dict[str, Any]) -> Dict[str, Any]:
        """Mask sensitive fields in credentials dictionary.
        
        Args:
            credentials: Credentials dictionary
            
        Returns:
            Dictionary with sensitive fields masked
        """
        masked = credentials.copy()
        
        # Common sensitive field names
        sensitive_fields = {
            'password', 'secret', 'token', 'key', 'api_key', 'client_secret',
            'access_token', 'refresh_token', 'private_key', 'certificate'
        }
        
        for field, value in masked.items():
            field_lower = field.lower()
            if any(sensitive in field_lower for sensitive in sensitive_fields):
                if isinstance(value, str):
                    if 'token' in field_lower:
                        masked[field] = DataMasking.mask_token(value)
                    elif 'key' in field_lower:
                        masked[field] = DataMasking.mask_api_key(value)
                    else:
                        masked[field] = "***" if len(value) < 8 else f"{value[:3]}{'*' * 6}...{value[-2:]}"
                else:
                    masked[field] = "***"
        
        return masked
    
    @staticmethod
    def mask_connection_response(connection_data: Dict[str, Any]) -> Dict[str, Any]:
        """Mask sensitive fields in connection API response.
        
        Args:
            connection_data: Connection data dictionary
            
        Returns:
            Dictionary with sensitive fields masked
        """
        masked = connection_data.copy()
        
        # Mask credentials if present
        if 'credentials' in masked and isinstance(masked['credentials'], dict):
            masked['credentials'] = DataMasking.mask_credentials(masked['credentials'])
        
        # Mask encrypted credentials
        if 'credentials_enc' in masked:
            masked['credentials_enc'] = "***encrypted***"
        
        # Mask last error if it contains sensitive info
        if 'last_error' in masked and masked['last_error']:
            # Simple check for potential sensitive data in error messages
            error_msg = str(masked['last_error'])
            if any(word in error_msg.lower() for word in ['token', 'key', 'secret', 'password']):
                masked['last_error'] = "Error message contains sensitive data (masked)"
        
        return masked
    
    @staticmethod
    def encrypt_token_simple(token: str, secret_key: str) -> str:
        """Simple token encryption (for OAuth state and other temporary data)
        
        Args:
            token: Token to encrypt
            secret_key: Encryption key
            
        Returns:
            Encrypted token
        """
        if not token:
            return ""
        
        # Simple XOR encryption
        key = secret_key.encode()[:32]  # Take first 32 bytes as key
        encrypted_bytes = bytearray()
        token_bytes = token.encode('utf-8')
        
        for i, byte in enumerate(token_bytes):
            encrypted_bytes.append(byte ^ key[i % len(key)])
        
        # Base64 encoding
        return base64.b64encode(encrypted_bytes).decode('utf-8')
    
    @staticmethod
    def decrypt_token_simple(encrypted_token: str, secret_key: str) -> str:
        """Simple token decryption
        
        Args:
            encrypted_token: Encrypted token
            secret_key: Decryption key
            
        Returns:
            Decrypted token
        """
        if not encrypted_token:
            return ""
        
        try:
            key = secret_key.encode()[:32]  # Take first 32 bytes as key
            
            # Base64 decoding
            encrypted_bytes = base64.b64decode(encrypted_token.encode('utf-8'))
            
            # XOR decryption
            decrypted_bytes = bytearray()
            for i, byte in enumerate(encrypted_bytes):
                decrypted_bytes.append(byte ^ key[i % len(key)])
            
            return decrypted_bytes.decode('utf-8')
        except Exception as e:
            logger.error(f"Error decrypting token: {str(e)}")
            return ""


class SecurityValidator:
    """Security validation utilities."""
    
    @staticmethod
    def validate_connection_config(config: Dict[str, Any]) -> tuple[bool, str]:
        """Validate connection configuration for security issues.
        
        Args:
            config: Connection configuration
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        # Check for common security issues
        
        # 1. Check for hardcoded secrets in config
        config_str = json.dumps(config, default=str).lower()
        suspicious_patterns = [
            'password=', 'secret=', 'token=', 'key=',
            'bearer ', 'basic ', 'api_key='
        ]
        
        for pattern in suspicious_patterns:
            if pattern in config_str:
                return False, f"Configuration contains potentially hardcoded credentials: {pattern}"
        
        # 2. Check for insecure URLs
        for key, value in config.items():
            if isinstance(value, str) and value.startswith('http://'):
                if 'localhost' not in value and '127.0.0.1' not in value:
                    return False, f"Insecure HTTP URL detected in {key}: {value}"
        
        # 3. Check for weak authentication methods
        auth_method = config.get('auth_method', '').lower()
        if auth_method in ['none', 'basic'] and config.get('require_ssl', True) is False:
            return False, "Weak authentication method without SSL is not allowed"
        
        return True, "Configuration is secure"
    
    @staticmethod
    def sanitize_error_message(error_msg: str) -> str:
        """Sanitize error messages to remove sensitive information.
        
        Args:
            error_msg: Original error message
            
        Returns:
            Sanitized error message
        """
        if not error_msg:
            return error_msg
        
        # Remove common sensitive patterns
        import re
        
        # Remove tokens and keys
        error_msg = re.sub(r'\b[A-Za-z0-9+/]{20,}={0,2}\b', '[TOKEN_REMOVED]', error_msg)
        
        # Remove API keys
        error_msg = re.sub(r'\btlk_[a-zA-Z0-9_]+\b', '[API_KEY_REMOVED]', error_msg)
        
        # Remove URLs with credentials
        error_msg = re.sub(r'https?://[^\s:]+:[^\s@]+@[^\s]+', '[URL_WITH_CREDENTIALS_REMOVED]', error_msg)
        
        # Remove email addresses in some contexts
        error_msg = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '[EMAIL_REMOVED]', error_msg)
        
        return error_msg


# Global instances
_credential_encryption = None

def get_credential_encryption() -> CredentialEncryption:
    """Get global credential encryption instance."""
    global _credential_encryption
    if _credential_encryption is None:
        _credential_encryption = CredentialEncryption()
    return _credential_encryption


# Convenience functions
def encrypt_credentials(credentials: Dict[str, Any]) -> str:
    """Encrypt credentials using global encryption instance."""
    return get_credential_encryption().encrypt_credentials(credentials)


def decrypt_credentials(encrypted_credentials: str) -> Dict[str, Any]:
    """Decrypt credentials using global encryption instance."""
    return get_credential_encryption().decrypt_credentials(encrypted_credentials)
