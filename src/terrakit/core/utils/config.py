from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    
    DB_URL: str = Field("sqlite:///./terrakit_platform.db", alias="TL_DB_URL")
    JWT_SECRET: str = Field("dev_jwt_change_me", alias="TL_JWT_SECRET")
    JWT_EXPIRE_MIN: int = 60
    APIKEY_KDF_SECRET: str = Field("dev_apikey_kdf_change_me", alias="TL_APIKEY_KDF_SECRET")  # HMAC salt
    ENV: str = Field("dev", alias="TL_ENV")
    
    # OAuth configuration
    OAUTH_REDIRECT_URI: str = Field("http://localhost:3000/auth/callback", alias="OAUTH_REDIRECT_URI")
    GITHUB_OAUTH_CLIENT_ID: str = Field("", alias="GITHUB_OAUTH_CLIENT_ID")
    GITHUB_OAUTH_CLIENT_SECRET: str = Field("", alias="GITHUB_OAUTH_CLIENT_SECRET")
    GOOGLE_OAUTH_CLIENT_ID: str = Field("", alias="GOOGLE_OAUTH_CLIENT_ID")
    GOOGLE_OAUTH_CLIENT_SECRET: str = Field("", alias="GOOGLE_OAUTH_CLIENT_SECRET")
    
    # Additional OAuth providers (optional)
    MICROSOFT_OAUTH_CLIENT_ID: str = Field("", alias="MICROSOFT_OAUTH_CLIENT_ID")
    MICROSOFT_OAUTH_CLIENT_SECRET: str = Field("", alias="MICROSOFT_OAUTH_CLIENT_SECRET")
    DISCORD_OAUTH_CLIENT_ID: str = Field("", alias="DISCORD_OAUTH_CLIENT_ID")
    DISCORD_OAUTH_CLIENT_SECRET: str = Field("", alias="DISCORD_OAUTH_CLIENT_SECRET")
    LINKEDIN_OAUTH_CLIENT_ID: str = Field("", alias="LINKEDIN_OAUTH_CLIENT_ID")
    LINKEDIN_OAUTH_CLIENT_SECRET: str = Field("", alias="LINKEDIN_OAUTH_CLIENT_SECRET")
    
    # Stripe, Redis, CORS whitelist, etc.
    # STRIPE_SECRET: str | None = None
    # REDIS_URL: str | None = None

settings = Settings()