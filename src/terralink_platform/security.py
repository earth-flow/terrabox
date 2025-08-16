"""Security utilities for password hashing, JWT tokens, and API key management."""

from datetime import datetime, timedelta
from typing import Optional
from passlib.context import CryptContext
from jose import JWTError, jwt
import secrets
import hashlib
import hmac

from .config import settings

def generate_public_id() -> str:
    """生成API Key的公开ID"""
    return secrets.token_urlsafe(12)

# 密码加密上下文
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

def hash_password(password: str) -> str:
    """哈希密码"""
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码"""
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """创建JWT访问令牌"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.JWT_EXPIRE_MIN)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET, algorithm="HS256")
    return encoded_jwt

def verify_token(token: str) -> Optional[dict]:
    """验证JWT令牌"""
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
        return payload
    except JWTError:
        return None

def generate_api_key(prefix: str = "live") -> str:
    """生成API密钥，支持prefix参数"""
    key_part = secrets.token_urlsafe(32)
    return f"tlk_{prefix}_{key_part}"

def generate_public_id() -> str:
    """生成API密钥的公开ID"""
    return secrets.token_urlsafe(12)

def mask_key(full_key: str) -> str:
    """遮蔽API密钥用于日志，只显示前缀和部分字符"""
    if not full_key or len(full_key) < 10:
        return "tlk_***"
    
    # 如果是新格式的key (tlk_prefix_xxxxx)
    if full_key.startswith("tlk_"):
        parts = full_key.split("_", 2)
        if len(parts) >= 3:
            prefix = parts[1]
            return f"tlk_{prefix}_{'*' * 8}...{full_key[-4:]}"
    
    # 兼容旧格式或其他格式
    return f"tlk_***...{full_key[-4:]}"

def hash_api_key(api_key: str) -> str:
    """使用HMAC哈希API密钥"""
    return hmac.new(
        settings.APIKEY_KDF_SECRET.encode(),
        api_key.encode(),
        hashlib.sha256
    ).hexdigest()

def validate_password_strength(password: str) -> tuple[bool, str]:
    """验证密码强度"""
    if len(password) < 8:
        return False, "密码长度至少8位"
    
    has_upper = any(c.isupper() for c in password)
    has_lower = any(c.islower() for c in password)
    has_digit = any(c.isdigit() for c in password)
    has_special = any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in password)
    
    if not (has_upper and has_lower and has_digit):
        return False, "密码必须包含大写字母、小写字母和数字"
    
    return True, "密码强度符合要求"