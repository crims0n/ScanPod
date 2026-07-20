from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_prefix": "SCANPOD_"}

    api_key: str = "changeme"
    scan_timeout: int = 900
    max_scan_workers: int = 4
    allow_unsafe_args: bool = False
    max_jobs: int = 1000
    job_ttl_seconds: int = 3600
    log_level: str = "INFO"
    log_file: str = ""


settings = Settings()
