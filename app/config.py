"""IMSF-v2 settings — from environment variables only.

No hardcoded secrets and no hardcoded GPU IP. Copy `.env.example` to
`.env` (or use the host env file `/home/ubuntu/imsf-v2.env`) and fill in
real values. GPU_HOST is the ephemeral IP of the GPU VM running Ollama;
update it whenever that VM restarts.
"""

import os


class Settings:
    database_url: str = os.environ.get(
        "DATABASE_URL", "postgresql+psycopg://imsf_v2:imsf_v2@127.0.0.1:55434/imsf_v2"
    )
    redis_url: str = os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0")
    jwt_secret: str = os.environ.get("JWT_SECRET", "change-me-in-production")
    gpu_host: str = os.environ.get("GPU_HOST", "")
    # Ollama is reached through the SSH tunnel on localhost:11434
    # (see ollama-tunnel.service); never point this at the GPU IP directly.
    ollama_base_url: str = os.environ.get(
        "OLLAMA_BASE_URL", "http://127.0.0.1:11434"
    )
    ocr_provider: str = os.environ.get("OCR_PROVIDER", "baidu")
    baidu_api_key: str = os.environ.get("BAIDU_API_KEY", "")
    baidu_secret_key: str = os.environ.get("BAIDU_SECRET_KEY", "")
    wechat_appid: str = os.environ.get("WECHAT_APPID", "")
    wechat_secret: str = os.environ.get("WECHAT_SECRET", "")
    # Eval/demo-only service token (never shipped in a client). Empty =
    # service-token auth disabled.
    service_token: str = os.environ.get("IMSF_V2_SERVICE_TOKEN", "")
    receipt_storage_dir: str = os.environ.get(
        "RECEIPT_STORAGE_DIR", "/var/lib/imsf-v2/receipts"
    )
    ocr_timeout_seconds: float = float(os.environ.get("OCR_TIMEOUT_SECONDS", "25"))
    qwen_timeout_seconds: float = float(os.environ.get("QWEN_TIMEOUT_SECONDS", "120"))


settings = Settings()
