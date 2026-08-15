from typing import Annotated

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str
    jwt_secret: Annotated[SecretStr, Field(min_length=32)]

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
