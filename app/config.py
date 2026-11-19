"""IMSF-v2 settings — from environment variables only.

No hardcoded secrets and no hardcoded GPU IP. Copy `.env.example` to
`.env` (or use the host env file `/home/ubuntu/imsf-v2.env`) and fill in
real values. GPU_HOST is the ephemeral IP of the GPU VM running Ollama;
update it whenever that VM restarts.
"""

import os


class Settings:
    database_url: str = os.environ.get(
        "DATABASE_URL", "postgresql+psycopg://127.0.0.1:55434/imsf_v2"
    )
    redis_url: str = os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0")
    jwt_secret: str = os.environ.get("JWT_SECRET", "")
    gpu_host: str = os.environ.get("GPU_HOST", "")


settings = Settings()
