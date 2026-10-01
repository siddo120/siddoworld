"""Configuration for Mealyn.

Secrets come from the environment (see ``.env.example``). Every external rail
degrades to a STUB when its credentials are missing, so the full agent loop runs
offline for development. ``ANTHROPIC_API_KEY`` is the one that makes the
reasoning genuinely intelligent; without it the brain falls back to a
deterministic stub planner.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class WhatsAppSettings(BaseModel):
    token: str = ""
    phone_number_id: str = ""
    verify_token: str = "mealyn-verify"
    api_base: str = "https://graph.facebook.com/v19.0"

    @property
    def live(self) -> bool:
        return bool(self.token and self.phone_number_id)


class GnaniSettings(BaseModel):
    api_key: str = ""
    prisma_url: str = ""  # speech-to-text
    timbre_url: str = ""  # text-to-speech

    @property
    def live(self) -> bool:
        return bool(self.api_key)


class PaymentSettings(BaseModel):
    provider: str = "paytm"
    merchant_id: str = ""
    api_key: str = ""

    @property
    def live(self) -> bool:
        return bool(self.merchant_id and self.api_key)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MEALYN_",
        env_nested_delimiter="__",
        env_file=".env",
        extra="ignore",
    )

    env: str = "development"
    timezone: str = "Asia/Kolkata"

    # Claude brain
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    model: str = "claude-opus-5-5"

    whatsapp: WhatsAppSettings = WhatsAppSettings()
    gnani: GnaniSettings = GnaniSettings()
    payment: PaymentSettings = PaymentSettings()

    @property
    def brain_live(self) -> bool:
        return bool(self.anthropic_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
