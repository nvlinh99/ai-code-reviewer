from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    GITLAB_API: str = "https://gitlab.com/api/v4"
    GITLAB_TOKEN: str
    OPENAI_API_KEY: str
    PROJECT_ID: str
    POSTGRES_DSN: str
    MODEL: str = "gpt-4-turbo-2024-04-09"
    GITLAB_WEBHOOK_SECRET : str 

    class Config:
        env_file = ".env"

settings = Settings()
