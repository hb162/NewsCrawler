"""
Entry point của ứng dụng NewsCrawler.
...
"""
from __future__ import annotations

import logging
import sys

from fastapi import FastAPI

from app.config import LOG_LEVEL
from app.db import init_db
from app.routes import router

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(
    title="NewsCrawler",
    description="Crawl tin HNX/HSX và bài thị trường chứng khoán từ CafeF",
    version="1.0.0",
)

app.include_router(router)


@app.on_event("startup")
def startup_event():
    """Tạo các bảng trading_changes và cafef_articles khi app khởi động."""
    logger.info("App starting up; initialising NewsCrawler tables...")
    init_db()
    logger.info("App ready (HNX, HSX, CafeF).")


# ---------------------------------------------------------------------------
# __main__: chạy trực tiếp trong PyCharm (reload=False để breakpoint hoạt động)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,           # truyền object trực tiếp — PyCharm có thể đặt breakpoint
        host="0.0.0.0",
        port=8000,
        reload=False,  # KHÔNG dùng reload khi debug
        log_level=LOG_LEVEL.lower(),
    )
