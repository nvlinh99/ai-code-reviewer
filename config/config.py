from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    GITLAB_API: str
    GITLAB_TOKEN: str
    OPENAI_API_KEY: str
    PROJECT_ID: str
    POSTGRES_DSN: str
    MODEL: str
    GITLAB_WEBHOOK_SECRET: str
    MODEL_PROVIDER: str
    MAX_TOKENS: int
    TEMPERATURE: float
    TOP_P: float 
    GITHUB_TOKEN: str 
    SYSTEM_PROMPT: str
    MODEL_ID: str

    class Config:
        env_file = ".env"
        env_file_encoding = 'utf-8'

settings = Settings()
