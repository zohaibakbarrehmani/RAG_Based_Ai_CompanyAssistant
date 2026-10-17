from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    project_name: str = "company-knowledge-ai"
    app_env: str = "development"
    backend_cors_origins: list[str] = [
        "http://localhost:3000",
        "http://localhost:3001",
    ]
    jwt_secret: str = "change_me"
    gemini_api_key: str = ""
    gemini_embed_model: str = "gemini-embedding-001"
    gemini_fast_model: str = "gemini-3.5-flash"    # fast routing/rewrite
    gemini_answer_model: str = "gemini-3.5-flash"  # primary answer model
    embedding_batch_size: int = 100
    retrieval_top_k: int = 14                       # fetch more candidates
    retrieval_keep: int = 6                         # pass more context to LLM
    min_similarity: float = 0.45                    # don't miss relevant chunks
    max_context_tokens: int = 6000                  # wider context window
    max_output_tokens: int = 900                    # avoid truncated answers


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
