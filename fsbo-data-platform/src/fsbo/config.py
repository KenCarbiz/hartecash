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

    # Twilio messaging. Leave blank to disable SMS send (returns a no-op
    # response that still records the Message row with status=skipped).
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_messaging_service_sid: str = ""  # preferred, for A2P 10DLC
    twilio_from_number: str = ""  # fallback if no messaging service
    twilio_status_callback: str = ""  # public https URL for delivery status

    # Marketcheck — legal paid aggregator for Autotrader/Cars.com/CarGurus
    # content we deliberately don't scrape. Blank = adapter yields nothing.
    marketcheck_api_key: str = ""

    # Auth.
    # env_mode: "dev" allows X-Dealer-Id header fallback; "production"
    # requires a real session cookie or API key.
    env_mode: str = "dev"
    # MUST be overridden in production via JWT_SECRET env var; HS256 wants >=32 bytes.
    jwt_secret: str = "change-me-in-production-dev-only-32-bytes-min"
    jwt_alg: str = "HS256"
    # How long a signed-in session lasts (days).
    session_days: int = 14
    # Public cookie domain, if needed for cross-subdomain setups.
    cookie_domain: str = ""
    cookie_secure: bool = False  # set True in production (HTTPS only)


settings = Settings()
