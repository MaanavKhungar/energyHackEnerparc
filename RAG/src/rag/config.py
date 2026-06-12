from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    collection_name: str = "energy_docs"
    embedding_model: str = "BAAI/bge-m3"
    ollama_model: str = "llama3.1:8b"
    ollama_host: str = "http://localhost:11434"
    chunk_size: int = 512
    chunk_overlap: int = 50
    retrieval_top_k: int = 5

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
