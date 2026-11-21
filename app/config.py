"""IMSF settings — from environment variables only.

No hardcoded secrets and no hardcoded GPU IP. Copy `.env.example` to
`.env` (or use the host env file `/home/ubuntu/imsf.env`) and fill in
real values. GPU_HOST is the ephemeral IP of the GPU VM running Ollama;
update it whenever that VM restarts.
"""

import os


class Settings:
    database_url: str = os.environ.get(
        "DATABASE_URL", "postgresql+psycopg://imsf:imsf@127.0.0.1:55434/imsf"
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
    # WeChat template IDs for Phase 2 notifications (design §8).
    # Empty = templates not registered yet; app.jobs.send_wechat
    # skips sending until all four WeChat vars are set.
    wechat_template_lazy_tracking: str = os.environ.get(
        "WECHAT_TEMPLATE_LAZY_TRACKING", ""
    )
    wechat_template_maintenance: str = os.environ.get(
        "WECHAT_TEMPLATE_MAINTENANCE", ""
    )
    # Eval/demo-only service token (never shipped in a client). Empty =
    # service-token auth disabled.
    service_token: str = os.environ.get("IMSF_SERVICE_TOKEN", "")
    receipt_storage_dir: str = os.environ.get(
        "RECEIPT_STORAGE_DIR", "/var/lib/imsf/receipts"
    )
    ocr_timeout_seconds: float = float(os.environ.get("OCR_TIMEOUT_SECONDS", "25"))
    qwen_timeout_seconds: float = float(os.environ.get("QWEN_TIMEOUT_SECONDS", "120"))


settings = Settings()
