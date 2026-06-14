"""
Đọc toàn bộ cấu hình từ .env.
Không có side-effect khi import — chỉ là namespace chứa các hằng số.
"""
from __future__ import annotations

import os
from dotenv import load_dotenv

load_dotenv()

# ---- Database ----
# psycopg3 yêu cầu scheme "postgresql://...", không phải "+psycopg"
_raw_db_url: str = os.environ["DATABASE_URL"]
DATABASE_URL: str = _raw_db_url.replace("postgresql+psycopg://", "postgresql://")

# ---- Anthropic ----
ANTHROPIC_API_KEY: str = os.environ["ANTHROPIC_API_KEY"]
ANTHROPIC_MODEL: str = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5")

# ---- Crawl behaviour ----
CLASSIFY_BATCH_SIZE: int = int(os.getenv("CLASSIFY_BATCH_SIZE", "20"))
DEFAULT_CRAWL_HOURS: float = float(os.getenv("DEFAULT_CRAWL_HOURS", "1"))

# ---- HTTP client ----
HTTP_TIMEOUT: float = float(os.getenv("HTTP_TIMEOUT", "30"))

# ---- LLM retry ----
LLM_MAX_RETRIES: int = int(os.getenv("LLM_MAX_RETRIES", "3"))

# ---- Logging ----
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()

# ---- LLM limits ----
# Số trang PDF tối đa gửi cho LLM (tránh vượt token)
PDF_MAX_PAGES: int = int(os.getenv("PDF_MAX_PAGES", "10"))
