from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # BurgerPrints API
    BURGERPRINTS_API_KEY: str = ""
    BURGERPRINTS_API_BASE_URL: str = "https://api.burgerprints.com/v2"
    
    # AI Models
    GEMINI_API_KEY: str = ""
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

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()
