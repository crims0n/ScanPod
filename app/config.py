from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_prefix": "SCANPOD_"}

    api_key: str = "changeme"
    scan_timeout: int = 300
    max_scan_workers: int = 4


settings = Settings()
