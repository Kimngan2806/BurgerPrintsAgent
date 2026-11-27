from pydantic_settings import BaseSettings, SettingsConfigDict


def normalize_store_display_name(value: str) -> str:
    name = value.strip()
    # Existing deployments may still have the old placeholder in their environment.
    if name.casefold() in {"", "burgerprints demo", "store demo cấu hình trên máy chủ"}:
        return "BurgerPrints"
    return name


class Settings(BaseSettings):
    # BurgerPrints API
    BURGERPRINTS_API_KEY: str = ""
    BURGERPRINTS_API_BASE_URL: str = "https://api.burgerprints.com/v2"
    
    # AI Models
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-3.1-flash-lite"
    GEMINI_FALLBACK_MODEL: str = "gemini-3.6-flash"
    OPENROUTER_API_KEY: str = ""
    OPENROUTER_MODEL: str = "cohere/north-mini-code:free"
    VIETCOD_API_KEY: str = ""
    VIETCOD_MODEL: str = "gemini-3.8-flash-high"
    SEEDANCE_API_KEY: str = ""
    PRIMARY_MODEL_PROVIDER: str = "byteplus"
    BYTEPLUS_API_BASE_URL: str = "https://ark.ap-southeast.bytepluses.com/api/v3"
    BYTEPLUS_MODEL: str = "seed-2-0-lite-260228"
    FALLBACK_MODEL_PROVIDER: str = "byteplus"
    GOOGLE_CLOUD_PROJECT: str = ""
    GOOGLE_CLOUD_LOCATION: str = "us-central1"
    VERTEX_MODEL: str = "gemini-2.5-flash"
    GOOGLE_APPLICATION_CREDENTIALS: str = "/app/secrets/vertex-service-account.json"
    
    # Feature Flags
    HARNESS_FF_SDK_KEY: str = ""
    
    # App Config
    SESSION_TTL_MINUTES: int = 30
    CACHE_SYNC_ON_STARTUP: bool = False
    BUILD_SEARCH_INDEX_ON_STARTUP: bool = False
    DUCKDB_PATH: str = "catalog.duckdb"
    WORKSPACE_DB_PATH: str = "data/workspace.sqlite3"
    WORKSPACE_DATABASE_URL: str = ""
    FILE_STORAGE_PATH: str = "data/designs"
    PUBLIC_FILE_BASE_URL: str = ""
    STORE_DISPLAY_NAME: str = "BurgerPrints"
    ORDER_SANDBOX: bool = True
    ENABLE_ORDER_SUBMISSION: bool = False
    STORE_TRANSACTION_NOTICE: str = ""
    COOKIE_SECURE: bool = False
    CORS_ORIGINS: str = "http://localhost:3000"
    CATALOG_SYNC_INTERVAL_SECONDS: int = 21600
    CATALOG_MAX_AGE_SECONDS: int = 86400

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def display_store_name(self) -> str:
        return normalize_store_display_name(self.STORE_DISPLAY_NAME)

settings = Settings()
