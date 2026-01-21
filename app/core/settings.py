
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import Optional

# Common Config for all settings classes to pick up .env
settings_config = SettingsConfigDict(
    env_file=".env",
    env_file_encoding="utf-8",
    extra="ignore"
)

class GroqSettings(BaseSettings):
    api_key: str = Field(..., alias="GROQ_API_KEY")
    base_url: str = Field("https://api.groq.com/openai/v1", alias="GROQ_BASE_URL")
    default_model: str = Field("llama-3.3-70b-versatile", alias="GROQ_DEFAULT_MODEL")
    
    model_config = settings_config

class GeminiSettings(BaseSettings):
    api_key: str = Field(..., alias="GEMINI_API_KEY")
    base_url: str = Field("https://generativelanguage.googleapis.com/v1beta/openai/", alias="GEMINI_BASE_URL")

    model_config = settings_config

class SelfHostedSettings(BaseSettings):
    base_url: str = Field("http://localhost:8001/v1", alias="SELF_HOSTED_BASE_URL")
    api_key: str = Field("none", alias="SELF_HOSTED_API_KEY")
    default_model: str = Field("qwen2.5:0.5b", alias="SELF_HOSTED_DEFAULT_MODEL")

    model_config = settings_config

class LLMSettings(BaseSettings):
    primary_provider: str = Field("self_hosted", alias="LLM_PRIMARY_PROVIDER")
    fallback_provider: str = Field("groq", alias="LLM_FALLBACK_PROVIDER")
    production_provider: str = Field("self_hosted", alias="LLM_PRODUCTION_PROVIDER")
    sql_provider: str = Field("groq", alias="LLM_SQL_PROVIDER")
    embedding_provider: str = Field("local", alias="EMBEDDING_PROVIDER")
    embedding_model: str = Field("sentence-transformers/all-MiniLM-L6-v2", alias="EMBEDDING_MODEL_NAME")
    
    understanding_model: str = Field("llama-3.3-70b-versatile", alias="LLM_UNDERSTANDING_MODEL")
    reply_model: str = Field("llama-3.3-70b-versatile", alias="LLM_REPLY_MODEL")
    sql_model: str = Field("llama-3.3-70b-versatile", alias="LLM_SQL_MODEL")

    model_config = settings_config

class DatabaseSettings(BaseSettings):
    url: str = Field(..., alias="DATABASE_URL")
    pool_size: int = Field(5, alias="DB_POOL_SIZE")
    max_overflow: int = Field(10, alias="DB_MAX_OVERFLOW")

    model_config = settings_config

class AppSettings(BaseSettings):
    env: str = Field("development", alias="APP_ENV")
    log_level: str = Field("INFO", alias="LOG_LEVEL")
    
    # Using default_factory with BaseSettings classes will now trigger their own env loading
    groq: GroqSettings = Field(default_factory=GroqSettings)
    gemini: GeminiSettings = Field(default_factory=GeminiSettings)
    self_hosted: SelfHostedSettings = Field(default_factory=SelfHostedSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    db: DatabaseSettings = Field(default_factory=DatabaseSettings)
    auth: "AuthSettings" = Field(default_factory=lambda: AuthSettings())
    elasticsearch: "ElasticsearchSettings" = Field(default_factory=lambda: ElasticsearchSettings())
    redis: "RedisSettings" = Field(default_factory=lambda: RedisSettings())

    model_config = settings_config

class ElasticsearchSettings(BaseSettings):
    url: str = Field("http://elasticsearch:9200", alias="ELASTICSEARCH_URL")
    
    model_config = settings_config

class RedisSettings(BaseSettings):
    url: str = Field("redis://redis:6379", alias="REDIS_URL")

    model_config = settings_config

class AuthSettings(BaseSettings):
    secret_key: str = Field("dev_secret_key_change_in_prod", alias="SECRET_KEY")
    algorithm: str = Field("HS512", alias="ALGORITHM")
    access_token_expire_minutes: int = Field(30, alias="ACCESS_TOKEN_EXPIRE_MINUTES")
    
    model_config = settings_config

    model_config = settings_config

settings = AppSettings()
