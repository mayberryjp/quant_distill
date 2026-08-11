from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", env_file=".env", env_file_encoding="utf-8")

    api_listen_address: str = Field("0.0.0.0", validation_alias="API_LISTEN_ADDRESS")  # nosec B104
    api_port: int = Field(8021, validation_alias="API_PORT")
    log_level: str = Field("INFO", validation_alias="LOG_LEVEL")

    llm_base_url: str = Field(
        "http://localhost:11434/v1/chat/completions",
        validation_alias="LLM_BASE_URL",
    )
    llm_model: str = Field("llama3.1", validation_alias="LLM_MODEL")
    llm_api_key: str = Field("", validation_alias="LLM_API_KEY")
    llm_timeout: int = Field(60, validation_alias="LLM_TIMEOUT")
    llm_max_tokens: int = Field(4096, validation_alias="LLM_MAX_TOKENS")
    llm_json_mode: bool = Field(True, validation_alias="LLM_JSON_MODE")
    llm_num_ctx: int = Field(16384, validation_alias="LLM_NUM_CTX")

    distill_prompt_version: str = Field("v1", validation_alias="DISTILL_PROMPT_VERSION")
    sentiment_prompt_version: str = Field("v1", validation_alias="SENTIMENT_PROMPT_VERSION")
    entity_prompt_version: str = Field("v1", validation_alias="ENTITY_PROMPT_VERSION")
    distill_max_chunk_chars: int = Field(12000, validation_alias="DISTILL_MAX_CHUNK_CHARS")

    watchlist_api_url: str = Field("", validation_alias="WATCHLIST_API_URL")
    watchlist_api_key: str = Field("", validation_alias="WATCHLIST_API_KEY")
    watchlist_timeout: int = Field(15, validation_alias="WATCHLIST_TIMEOUT")
    watchlist_enabled: bool = Field(True, validation_alias="WATCHLIST_ENABLED")
    watchlist_required: bool = Field(False, validation_alias="WATCHLIST_REQUIRED")

    momentum_api_url: str = Field("", validation_alias="MOMENTUM_API_URL")
    momentum_api_key: str = Field("", validation_alias="MOMENTUM_API_KEY")
    momentum_timeout: int = Field(15, validation_alias="MOMENTUM_TIMEOUT")
    momentum_enabled: bool = Field(True, validation_alias="MOMENTUM_ENABLED")
    momentum_required: bool = Field(False, validation_alias="MOMENTUM_REQUIRED")

    http_retries: int = Field(3, validation_alias="HTTP_RETRIES")
    retry_backoff: float = Field(1.0, validation_alias="RETRY_BACKOFF")
    max_page_size: int = Field(100, validation_alias="MAX_PAGE_SIZE")
    prewarm_enabled: bool = Field(False, validation_alias="PREWARM_ENABLED")


settings = Settings()  # type: ignore[call-arg]
