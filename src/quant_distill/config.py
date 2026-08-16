from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    api_listen_address: str = Field("0.0.0.0", validation_alias="API_LISTEN_ADDRESS")  # nosec B104
    api_port: int = Field(8021, validation_alias="API_PORT")
    api_threads: int = Field(8, validation_alias="API_THREADS")
    log_level: str = Field("INFO", validation_alias="LOG_LEVEL")

    llm_base_url: str = Field(
        "http://localhost:11434/v1/chat/completions",
        validation_alias="LLM_BASE_URL",
    )
    llm_model: str = Field("llama3.1", validation_alias="LLM_MODEL")
    llm_api_key: str = Field("", validation_alias="LLM_API_KEY")
    llm_timeout: int = Field(300, validation_alias="LLM_TIMEOUT")
    llm_max_tokens: int = Field(4096, validation_alias="LLM_MAX_TOKENS")
    llm_json_mode: bool = Field(True, validation_alias="LLM_JSON_MODE")
    llm_num_ctx: int = Field(16384, validation_alias="LLM_NUM_CTX")

    distill_prompt_version: str = Field("v1", validation_alias="DISTILL_PROMPT_VERSION")
    sentiment_prompt_version: str = Field("v1", validation_alias="SENTIMENT_PROMPT_VERSION")
    entity_prompt_version: str = Field("v1", validation_alias="ENTITY_PROMPT_VERSION")
    distill_max_chunk_chars: int = Field(12000, validation_alias="DISTILL_MAX_CHUNK_CHARS")

    sentiment_api_url: str = Field("", validation_alias="SENTIMENT_API_URL")
    sentiment_api_key: str = Field("", validation_alias="SENTIMENT_API_KEY")
    sentiment_timeout: int = Field(30, validation_alias="SENTIMENT_TIMEOUT")
    sentiment_required: bool = Field(False, validation_alias="SENTIMENT_REQUIRED")

    signals_api_url: str = Field("", validation_alias="SIGNALS_API_URL")
    signals_api_key: str = Field("", validation_alias="SIGNALS_API_KEY")
    signals_timeout: int = Field(30, validation_alias="SIGNALS_TIMEOUT")
    signals_required: bool = Field(False, validation_alias="SIGNALS_REQUIRED")

    database_url: str = Field("", validation_alias="DATABASE_URL")

    http_retries: int = Field(3, validation_alias="HTTP_RETRIES")
    retry_backoff: float = Field(1.0, validation_alias="RETRY_BACKOFF")
    max_page_size: int = Field(100, validation_alias="MAX_PAGE_SIZE")


settings = Settings()  # type: ignore[call-arg]
