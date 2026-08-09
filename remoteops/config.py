from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = (
        "postgresql+psycopg://remoteops:remoteops@localhost:5432/remoteops"
    )

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
