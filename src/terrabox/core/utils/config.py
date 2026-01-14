import os

from dotenv import find_dotenv, load_dotenv
from pydantic import BaseModel, Field

class Settings(BaseModel):
    DB_URL: str = Field(default="sqlite:///./terrabox_platform.db")
    JWT_SECRET: str = Field(default="dev_jwt_change_me")
    JWT_EXPIRE_MIN: int = 60
    APIKEY_KDF_SECRET: str = Field(default="dev_apikey_kdf_change_me")
    ENV: str = Field(default="dev")

    OAUTH_REDIRECT_URI: str = Field(default="http://localhost:3000/auth/callback")
    GITHUB_OAUTH_CLIENT_ID: str = Field(default="")
    GITHUB_OAUTH_CLIENT_SECRET: str = Field(default="")
    GOOGLE_OAUTH_CLIENT_ID: str = Field(default="")
    GOOGLE_OAUTH_CLIENT_SECRET: str = Field(default="")

    MICROSOFT_OAUTH_CLIENT_ID: str = Field(default="")
    MICROSOFT_OAUTH_CLIENT_SECRET: str = Field(default="")
    DISCORD_OAUTH_CLIENT_ID: str = Field(default="")
    DISCORD_OAUTH_CLIENT_SECRET: str = Field(default="")
    LINKEDIN_OAUTH_CLIENT_ID: str = Field(default="")
    LINKEDIN_OAUTH_CLIENT_SECRET: str = Field(default="")


def _get_env(name: str, default: str) -> str:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value


def _load_settings() -> Settings:
    load_dotenv(find_dotenv(), override=False)
    default_env = "test" if os.getenv("PYTEST_CURRENT_TEST") else "dev"
    return Settings(
        DB_URL=_get_env("TL_DB_URL", "sqlite:///./terrabox_platform.db"),
        JWT_SECRET=_get_env("TL_JWT_SECRET", "dev_jwt_change_me"),
        JWT_EXPIRE_MIN=int(_get_env("TL_JWT_EXPIRE_MIN", "60")),
        APIKEY_KDF_SECRET=_get_env("TL_APIKEY_KDF_SECRET", "dev_apikey_kdf_change_me"),
        ENV=_get_env("TL_ENV", default_env),
        OAUTH_REDIRECT_URI=_get_env("OAUTH_REDIRECT_URI", "http://localhost:3000/auth/callback"),
        GITHUB_OAUTH_CLIENT_ID=_get_env("GITHUB_OAUTH_CLIENT_ID", ""),
        GITHUB_OAUTH_CLIENT_SECRET=_get_env("GITHUB_OAUTH_CLIENT_SECRET", ""),
        GOOGLE_OAUTH_CLIENT_ID=_get_env("GOOGLE_OAUTH_CLIENT_ID", ""),
        GOOGLE_OAUTH_CLIENT_SECRET=_get_env("GOOGLE_OAUTH_CLIENT_SECRET", ""),
        MICROSOFT_OAUTH_CLIENT_ID=_get_env("MICROSOFT_OAUTH_CLIENT_ID", ""),
        MICROSOFT_OAUTH_CLIENT_SECRET=_get_env("MICROSOFT_OAUTH_CLIENT_SECRET", ""),
        DISCORD_OAUTH_CLIENT_ID=_get_env("DISCORD_OAUTH_CLIENT_ID", ""),
        DISCORD_OAUTH_CLIENT_SECRET=_get_env("DISCORD_OAUTH_CLIENT_SECRET", ""),
        LINKEDIN_OAUTH_CLIENT_ID=_get_env("LINKEDIN_OAUTH_CLIENT_ID", ""),
        LINKEDIN_OAUTH_CLIENT_SECRET=_get_env("LINKEDIN_OAUTH_CLIENT_SECRET", ""),
    )


settings = _load_settings()
