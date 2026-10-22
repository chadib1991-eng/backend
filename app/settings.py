from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+psycopg://sababreeze:sababreeze@localhost:5432/sababreeze"
    cors_origins: str = "https://sababreeze.com,https://www.sababreeze.com"
    public_site_url: str = "https://sababreeze.com"

    sheets_webhook_url: str = ""
    sheets_webhook_secret: str = ""
    admin_token: str = ""

    meta_pixel_id: str = ""
    meta_capi_token: str = ""
    meta_graph_version: str = "v23.0"
    meta_test_event_code: str = ""

    tiktok_pixel_id: str = ""
    tiktok_access_token: str = ""
    tiktok_test_event_code: str = ""

    snap_pixel_id: str = ""
    snap_capi_token: str = ""

    # ipapi.is free key. Required for VPN and proxy flags. https://ipapi.is/
    ipapi_key: str = ""
    # Comma-separated UAE mobiles that skip the IP check. Default is the test number.
    checkout_bypass_phones: str = "0500000099"


settings = Settings()
