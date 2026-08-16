from typing import Annotated

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str
    jwt_secret: Annotated[SecretStr, Field(min_length=32)]
    auth_rate_limit: Annotated[int, Field(gt=0)] = 100
    auth_rate_window_seconds: Annotated[int, Field(gt=0)] = 60
    webhook_signing_secret: Annotated[SecretStr, Field(min_length=32)] | None = None
    webhook_allowed_hosts: str = ""
    webhook_worker_poll_seconds: Annotated[float, Field(gt=0)] = 5
    cors_allowed_origins: str = ""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
