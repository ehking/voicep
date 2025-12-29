from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", case_sensitive=False)

    MODEL_SIZE: str = "small"
    RETENTION_HOURS: int = 24
    MAX_MB: int = 20
    MAX_SECONDS: int = 300
    STORAGE_DIR: str = "./storage"
    WORKER_THREADS: int = 1
    BEAM_SIZE: int = 5
    VAD_FILTER: bool = True


settings = Settings()
