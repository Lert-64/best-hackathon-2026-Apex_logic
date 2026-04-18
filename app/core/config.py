from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "AssetVision OTG"
    OPENAI_API_KEY: str = "placeholder"
    DATABASE_URL: str = "postgresql+asyncpg://user:pass@localhost/db"

    class Config:
        env_file = ".env"

settings = Settings()