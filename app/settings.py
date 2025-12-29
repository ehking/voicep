from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", case_sensitive=False)

    MODEL_SIZE: str = "small"
    MODEL_DEVICE: str = "cpu"
    COMPUTE_TYPE: str = "int8"

    PROMPT_BALANCED: str = "محاوره فارسی. لحن روزمره را بنویس."
    PROMPT_NOISY: str = "صدا پرنویز است. فقط گفتار فارسی را با لحن محاوره‌ای بنویس."
    PROMPT_MUSIC_MIXED: str = "موسیقی یا ترانه را نادیده بگیر، فقط گفتار فارسی را بنویس."

    RETENTION_HOURS: int = 24
    MAX_MB: int = 20
    MAX_SECONDS: int = 300
    STORAGE_DIR: str = "./storage"
    WORKER_THREADS: int = 2
    MAX_QUEUE_SIZE: int = 100
    USE_MLM_CORRECTION: bool = False
    DEMUCS_ENABLED: bool = False


settings = Settings()
