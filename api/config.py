"""API-layer production settings"""

import os

from dotenv import load_dotenv
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    neo4j_uri: str = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    cors_origins_raw: str = os.environ.get("CORS_ORIGINS", "http://localhost:5173")
    port: int = int(os.environ.get("PORT", "8000"))

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins_raw.split(",") if origin.strip()]

    @field_validator("neo4j_uri")
    @classmethod
    def _require_tls_for_remote(cls, v: str) -> str:
        is_local = "localhost" in v or "127.0.0.1" in v
        if not is_local and not (v.startswith("neo4j+s://") or v.startswith("bolt+s://")):
            raise ValueError(
                f"NEO4J_URI {v!r} points at a non-local host without a TLS scheme "
                "(neo4j+s:// or bolt+s://) -- AuraDB requires TLS."
            )
        return v


settings = Settings()
