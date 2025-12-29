from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", case_sensitive=False)

    MODEL_SIZE: str = "small"
    MODEL_DEVICE: str = "cpu"
    COMPUTE_TYPE: str = "int8"
    INITIAL_PROMPT: str = (
        "این مکالمه درباره عشق و احساسات است. کلمات: عشق، لبخند، دل، زندگی، هر روز، هر شب، فاطمه، قشنگ، خونه، نمی‌خوام، می‌خندم"
    )
    RETENTION_HOURS: int = 24
    MAX_MB: int = 20
    MAX_SECONDS: int = 300
    STORAGE_DIR: str = "./storage"
    WORKER_THREADS: int = 2
    MAX_QUEUE_SIZE: int = 100
    BEAM_SIZE: int = 10
    VAD_FILTER: bool = True
    USE_MLM_CORRECTION: bool = False


settings = Settings()
