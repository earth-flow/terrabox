"""Authentication utilities for password hashing, JWT tokens, and API key management."""

from datetime import datetime, timedelta
from typing import Optional, Tuple
from passlib.context import CryptContext
from jose import JWTError, jwt
import secrets
import hmac
import hashlib
import logging
from .config import settings

logger = logging.getLogger(__name__)

def generate_public_id() -> str:
    """Generate public ID for API Key"""
    return secrets.token_urlsafe(12)

# Password encryption context - using only modern schemes that don't rely on deprecated crypt module
pwd_context = CryptContext(
    schemes=["argon2", "bcrypt"],
    deprecated="auto",
    # Explicitly disable schemes that use the deprecated crypt module
    argon2__rounds=12,
    bcrypt__rounds=12
)

def hash_password(password: str) -> str:
    """Hash password"""
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password"""
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> Tuple[str, int]:
    """Create JWT access token"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.JWT_EXPIRE_MIN)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET, algorithm="HS256")
    # Calculate expiration time (seconds)
    expires_in_seconds = int((expire - datetime.utcnow()).total_seconds())
    return encoded_jwt, expires_in_seconds

def verify_token(token: str) -> Optional[dict]:
    """Verify JWT token"""
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
        return payload
    except JWTError:
        return None

def generate_api_key(prefix: str = "live") -> str:
    """Generate API key with prefix parameter support"""
    key_part = secrets.token_urlsafe(32)
    return f"tlk_{prefix}_{key_part}"

# mask_key function moved to core.security.DataMasking.mask_api_key

def hash_api_key(api_key: str) -> str:
    """Hash API key using HMAC"""
    return hmac.new(
        settings.APIKEY_KDF_SECRET.encode(),
        api_key.encode(),
        hashlib.sha256
    ).hexdigest()

def validate_password_strength(password: str) -> tuple[bool, str]:
    """Validate password strength"""
    if len(password) < 8:
        return False, "Password must be at least 8 characters long"
    
    has_upper = any(c.isupper() for c in password)
    has_lower = any(c.islower() for c in password)
    has_digit = any(c.isdigit() for c in password)
    has_special = any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in password)
    
    if not (has_upper and has_lower and has_digit):
        return False, "Password must contain uppercase letters, lowercase letters, and numbers"
    
    return True, "Password strength meets requirements"

# Token encryption functions moved to core.security.CredentialEncryption
# Use encrypt_credentials/decrypt_credentials for secure token storage