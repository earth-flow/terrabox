from pydantic_settings import BaseSettings
from pydantic import Field

class Settings(BaseSettings):
    DB_URL: str = Field("sqlite:///./terralink_platform.db", env="TL_DB_URL")
    JWT_SECRET: str = Field("dev_jwt_change_me", env="TL_JWT_SECRET")
    JWT_EXPIRE_MIN: int = 60
    APIKEY_KDF_SECRET: str = Field("dev_apikey_kdf_change_me", env="TL_APIKEY_KDF_SECRET")  # HMAC 盐
    ENV: str = Field("dev", env="TL_ENV")
    # Stripe、Redis、CORS 白名单等
    # STRIPE_SECRET: str | None = None
    # REDIS_URL: str | None = None
    
    class Config:
        env_file = ".env"

settings = Settings()