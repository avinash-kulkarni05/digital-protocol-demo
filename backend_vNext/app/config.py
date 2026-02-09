"""
Configuration settings for backend_vNext.

Reads credentials from parent .env file and provides typed settings.
"""

import os
from pathlib import Path
from typing import Dict, Optional
from functools import lru_cache

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


# Resolve paths
BACKEND_VNEXT_DIR = Path(__file__).parent.parent
PROJECT_ROOT = BACKEND_VNEXT_DIR.parent
ENV_FILE = PROJECT_ROOT / ".env"


# Default quality thresholds
DEFAULT_QUALITY_THRESHOLDS = {
    "accuracy": 0.95,       # 95% minimum accuracy
    "completeness": 0.90,   # 90% required fields present
    "usdm_adherence": 0.90, # 90% USDM schema adherence (allow minor violations)
    "provenance": 0.95,     # 95% provenance coverage
}


class Settings(BaseSettings):
    """Application settings loaded from .env file."""

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database - NeonDB PostgreSQL
    database_url: str = Field(
        default="",
        alias="DATABASE_URL",
        description="PostgreSQL connection URL for NeonDB"
    )

    # Gemini API
    gemini_api_key: str = Field(
        default="",
        alias="GEMINI_API_KEY",
        description="Google Gemini API key"
    )

    # Azure OpenAI (optional fallback)
    azure_openai_api_key: Optional[str] = Field(
        default=None,
        alias="AZURE_OPENAI_API_KEY"
    )
    azure_openai_endpoint: Optional[str] = Field(
        default=None,
        alias="AZURE_OPENAI_ENDPOINT"
    )
    azure_openai_deployment: Optional[str] = Field(
        default=None,
        alias="AZURE_OPENAI_DEPLOYMENT"
    )
    azure_openai_api_version: Optional[str] = Field(
        default=None,
        alias="AZURE_OPENAI_API_VERSION"
    )

    # Redis for Celery (optional - defaults to Redis on localhost)
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        alias="REDIS_URL",
        description="Redis connection URL for Celery broker"
    )

    # Application settings
    debug: bool = Field(default=False, alias="DEBUG")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    # Extraction settings
    max_retries: int = Field(default=3, description="Max retries per module extraction")
    gemini_model: str = Field(default="gemini-2.5-pro", description="Gemini model for extraction")
    gemini_max_output_tokens: int = Field(default=65536, description="Max output tokens for Gemini")

    # Schema settings
    db_schema: str = Field(default="backend_vnext", description="PostgreSQL schema name")

    # Parallel execution settings
    max_parallel_agents: int = Field(
        default=3,
        description="Max concurrent module extractions within a wave"
    )
    wave_stagger_delay: float = Field(
        default=0.5,
        description="Delay in seconds between agent starts in same wave (to avoid rate limits)"
    )

    # Quality thresholds (use method to get with defaults)
    quality_accuracy_threshold: float = Field(
        default=0.95,
        description="Minimum accuracy score (0.0-1.0)"
    )
    quality_completeness_threshold: float = Field(
        default=0.90,
        description="Minimum completeness score (0.0-1.0)"
    )
    quality_usdm_adherence_threshold: float = Field(
        default=0.90,
        description="Minimum USDM schema adherence score (0.0-1.0)"
    )
    quality_provenance_threshold: float = Field(
        default=0.95,
        description="Minimum provenance coverage (0.0-1.0)"
    )

    # Quality retry settings
    max_quality_retries: int = Field(
        default=3,
        description="Max retries for quality failures per pass"
    )
    quality_retry_delay: float = Field(
        default=2.0,
        description="Delay in seconds between quality retries"
    )

    # API retry settings (for transient errors like 503, 429, timeouts)
    api_retry_max_attempts: int = Field(
        default=3,
        description="Max retry attempts for transient API errors"
    )
    api_retry_base_delay: float = Field(
        default=2.0,
        description="Base delay in seconds for exponential backoff"
    )
    api_retry_max_delay: float = Field(
        default=60.0,
        description="Maximum delay in seconds between retries"
    )
    api_retry_exponential_base: float = Field(
        default=2.0,
        description="Base for exponential backoff calculation"
    )

    @property
    def quality_thresholds(self) -> Dict[str, float]:
        """Get quality thresholds as dictionary."""
        return {
            "accuracy": self.quality_accuracy_threshold,
            "completeness": self.quality_completeness_threshold,
            "usdm_adherence": self.quality_usdm_adherence_threshold,
            "provenance": self.quality_provenance_threshold,
        }

    @computed_field
    @property
    def prompts_dir(self) -> Path:
        """Path to prompts directory."""
        return BACKEND_VNEXT_DIR / "prompts"

    @computed_field
    @property
    def schemas_dir(self) -> Path:
        """Path to schemas directory."""
        return BACKEND_VNEXT_DIR / "schemas"

    @computed_field
    @property
    def uploads_dir(self) -> Path:
        """
        Path to uploads directory.

        DEPRECATED: PDFs are now stored in database (file_data column).
        This directory is kept for backward compatibility and temporary files only.
        """
        return BACKEND_VNEXT_DIR / "uploads"

    @computed_field
    @property
    def outputs_dir(self) -> Path:
        """Path to outputs directory."""
        return BACKEND_VNEXT_DIR / "outputs"

    @computed_field
    @property
    def tmp_dir(self) -> Path:
        """Path to tmp directory for logs."""
        return BACKEND_VNEXT_DIR / "tmp"

    def get_database_url_with_schema(self) -> str:
        """Return database URL with schema search path."""
        url = self.database_url
        if "?" in url:
            return f"{url}&options=-csearch_path%3D{self.db_schema}"
        return f"{url}?options=-csearch_path%3D{self.db_schema}"


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


# Convenience accessors
settings = get_settings()
