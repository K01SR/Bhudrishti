import os
from typing import List, Optional, Union
from pydantic import AnyHttpUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "Bhu-Drishti 3D"
    PROJECT_DESCRIPTION: str = "National 3D ULPIN Generation & Vertical Property Mapping System"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    ENVIRONMENT: str = "development"

    # Security & JWT
    SECRET_KEY: str = "bhu_drishti_3d_super_secret_jwt_key_airoli_2026_cadastre"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours

    # Demo evaluation accounts password (env-overridable, never reused in production)
    DEMO_PASSWORD: str = "demo@2026"

    # Database
    POSTGRES_SERVER: str = "postgres"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "bhudrishti"
    POSTGRES_PASSWORD: str = "bhudrishti_secure_spatial_2026"
    POSTGRES_DB: str = "bhudrishti_3d"
    
    @property
    def DATABASE_URL(self) -> str:
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    @property
    def SYNC_DATABASE_URL(self) -> str:
        return f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    # Redis & Celery
    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379

    @property
    def CELERY_BROKER_URL(self) -> str:
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/0"

    @property
    def CELERY_RESULT_BACKEND(self) -> str:
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/0"

    # MinIO Storage
    MINIO_ENDPOINT: str = "minio:9000"
    MINIO_PUBLIC_ENDPOINT: str = "http://localhost:9000"
    MINIO_ROOT_USER: str = "minioadmin"
    MINIO_ROOT_PASSWORD: str = "minioadmin_secure_spatial"
    MINIO_BUCKET_NAME: str = "bhudrishti-assets"
    MINIO_USE_SSL: bool = False
    LOCAL_STORAGE_PATH: str = "/tmp/bhudrishti_storage"

    # Digital Signature (Ed25519)
    # No default keypair. A committed private key is not a secret, and one
    # shared across deployments would make every signature forgeable by anyone
    # holding the repository. The published demonstration pair now lives in
    # app.core.crypto and is reachable only while ENABLE_DEMO_MODE is on.
    # Generate a real pair with:
    #   python -c "from cryptography.hazmat.primitives.asymmetric import ed25519 as e; \
    #     k=e.Ed25519PrivateKey.generate(); print(k.private_bytes_raw().hex()); \
    #     print(k.public_key().public_bytes_raw().hex())"
    ED25519_PRIVATE_KEY_HEX: Optional[str] = None
    ED25519_PUBLIC_KEY_HEX: Optional[str] = None

    # Municipal / Demo Spatial Settings
    DEMO_PRECINCT_NAME: str = "Airoli Sector 8, Navi Mumbai"
    MAX_DEMO_FSI: float = 2.00
    PUBLIC_BASE_URL: str = "http://localhost:3000"

    # CORS
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="allow",
    )

    def _validate_prd(self) -> None:
        if self.ENVIRONMENT.lower() in ("production", "prod"):
            known_dev_only = (
                "bhu_drishti_3d_super_secret_jwt_key_airoli_2026_cadastre",
                "bhudrishti_secure_spatial_2026",
                "7a4d9526786c2e36b3df516147bb0630b9101d2d3a37c92b23c2a382c40c1110",
                "minioadmin_secure_spatial",
                "demo@2026",
            )
            if self.SECRET_KEY in known_dev_only:
                raise RuntimeError(
                    "SECRET_KEY is still set to the development default. "
                    "Set a strong random value via env before enabling prod mode."
                )
            if self.POSTGRES_PASSWORD in known_dev_only:
                raise RuntimeError(
                    "POSTGRES_PASSWORD is still set to the development default. "
                    "Set a strong random value via env before enabling prod mode."
                )
            if self.ED25519_PRIVATE_KEY_HEX in known_dev_only:
                raise RuntimeError(
                    "ED25519 key is still the development default. "
                    "Generate a new keypair via env before enabling prod mode."
                )
            if self.ED25519_PUBLIC_KEY_HEX in known_dev_only:
                raise RuntimeError(
                    "ED25519_PUBLIC_KEY_HEX is still the development default. "
                    "Generate a new keypair via env before enabling prod mode."
                )


settings = Settings()
settings._validate_prd()
