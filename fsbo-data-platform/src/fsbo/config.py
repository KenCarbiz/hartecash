from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://fsbo:fsbo@localhost:5432/fsbo"
    anthropic_api_key: str = ""
    ebay_app_id: str = ""
    ebay_cert_id: str = ""
    ebay_dev_id: str = ""
    ebay_marketplace: str = "EBAY_US"
    proxy_url: str = ""
    log_level: str = "INFO"


settings = Settings()
