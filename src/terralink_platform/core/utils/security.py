"""Security utilities for password hashing, JWT tokens, and API key management."""

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

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> Tuple[str, int]:
    """创建JWT访问令牌"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.JWT_EXPIRE_MIN)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET, algorithm="HS256")
    # 计算过期时间（秒）
    expires_in_seconds = int((expire - datetime.utcnow()).total_seconds())
    return encoded_jwt, expires_in_seconds

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

def encrypt_token(token: str) -> str:
    """加密令牌用于安全存储
    
    使用简单的Base64编码加密，实际生产环境应使用AES等更强的加密方案
    """
    if not token:
        return ""
    
    import base64
    # 使用简单的Base64编码（实际应使用AES等对称加密）
    # 为了演示目的，这里使用简单的编码方案
    key = settings.JWT_SECRET.encode()[:32]  # 取前32字节作为密钥
    
    # 简单的XOR加密
    encrypted_bytes = bytearray()
    token_bytes = token.encode('utf-8')
    
    for i, byte in enumerate(token_bytes):
        encrypted_bytes.append(byte ^ key[i % len(key)])
    
    # Base64编码
    return base64.b64encode(encrypted_bytes).decode('utf-8')

def decrypt_token(encrypted_token: str) -> str:
    """解密令牌
    
    对应encrypt_token的解密实现
    """
    if not encrypted_token:
        return ""
    
    try:
        import base64
        key = settings.JWT_SECRET.encode()[:32]  # 取前32字节作为密钥
        
        # Base64解码
        encrypted_bytes = base64.b64decode(encrypted_token.encode('utf-8'))
        
        # XOR解密
        decrypted_bytes = bytearray()
        for i, byte in enumerate(encrypted_bytes):
            decrypted_bytes.append(byte ^ key[i % len(key)])
        
        return decrypted_bytes.decode('utf-8')
    except Exception as e:
        logger.error(f"Error decrypting token: {str(e)}")
        return ""