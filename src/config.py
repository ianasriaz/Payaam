"""Payaam Centralized Configuration Settings.

Loads environment variables using Pydantic Settings for runtime validation.
Configured for Purelymail (SMTP/IMAP), AWS Bedrock, and DynamoDB.
"""

import sys
if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass

from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # AWS & Bedrock Configuration
    AWS_REGION: str = "us-east-1"
    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None
    BEDROCK_MODEL_SONNET: str = "anthropic.claude-3-5-sonnet-20241022-v2:0"
    BEDROCK_MODEL_HAIKU: str = "anthropic.claude-3-5-haiku-20241022-v1:0"

    # DynamoDB Tables
    DYNAMODB_TABLE_USERS: str = "Payaam_Users"
    DYNAMODB_TABLE_MISSIONS: str = "Payaam_Missions"
    DYNAMODB_TABLE_REGISTRY: str = "Payaam_ContactRegistry"

    # Purelymail SMTP / IMAP Configuration
    PURELYMAIL_SMTP_HOST: str = "smtp.purelymail.com"
    PURELYMAIL_SMTP_PORT: int = 465
    PURELYMAIL_IMAP_HOST: str = "imap.purelymail.com"
    PURELYMAIL_IMAP_PORT: int = 993
    PURELYMAIL_USER: Optional[str] = None
    PURELYMAIL_PASSWORD: Optional[str] = None
    PURELYMAIL_DEFAULT_FROM: str = "payaam@yourdomain.com"

    # Security & Encryption (Fernet 32-byte key for encrypting user SMTP passwords at rest)
    APP_ENCRYPTION_KEY: Optional[str] = None

    # Application & Anti-Spam Guardrails
    COLLISION_COOLDOWN_DAYS: int = 14
    MAX_OUTREACH_TARGETS: int = 5
    SESSION_TTL_HOURS: int = 72

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()
