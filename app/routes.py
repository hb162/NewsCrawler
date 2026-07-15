"""
FastAPI routes:
  POST /crawl/hnx    ?hours=<float>
  POST /crawl/hsx    ?hours=<float>
  POST /crawl/cafef  ?hours=<float>
  GET  /health
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from app.config import DEFAULT_CRAWL_HOURS
from app.fetchers import hnx as hnx_fetcher
from app.fetchers import hsx as hsx_fetcher
from app.pipeline import run_pipeline
from app.pipeline_cafef import run_cafef_pipeline

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health")
def health():
    return {"status": "ok"}


@router.post("/crawl/hnx")
def crawl_hnx(
    hours: float = Query(default=DEFAULT_CRAWL_HOURS, gt=0, description="Cửa sổ thời gian (giờ)")
):
    """Crawl tin HNX trong `hours` giờ gần nhất."""
    logger.info("POST /crawl/hnx hours=%.1f", hours)
    stats = run_pipeline(
        source="hnx",
        window_hours=hours,
        fetch_articles=lambda: hnx_fetcher.fetch_hnx_articles(hours),
        fetch_pdf_url=lambda art_id: _fetch_hnx_pdf_url(art_id),
        fetch_pdf_bytes=hnx_fetcher.fetch_pdf_bytes,
        article_id_key="article_id",
        published_at_key="date",
    )
    return JSONResponse(content=_serialize_stats(stats))


@router.post("/crawl/hsx")
def crawl_hsx(
    hours: float = Query(default=DEFAULT_CRAWL_HOURS, gt=0, description="Cửa sổ thời gian (giờ)")
):
    """Crawl tin HSX trong `hours` giờ gần nhất."""
    logger.info("POST /crawl/hsx hours=%.1f", hours)
    stats = run_pipeline(
        source="hsx",
        window_hours=hours,
        fetch_articles=lambda: hsx_fetcher.fetch_hsx_articles(hours),
        fetch_pdf_url=hsx_fetcher.fetch_hsx_pdf_url,
        fetch_pdf_bytes=hsx_fetcher.fetch_pdf_bytes,
        article_id_key="news_id",
        published_at_key="posted_at",
    )
    return JSONResponse(content=_serialize_stats(stats))


@router.post("/crawl/cafef")
def crawl_cafef(
    hours: float = Query(default=DEFAULT_CRAWL_HOURS, gt=0, description="Cửa sổ thời gian (giờ)")
):
    """Crawl bài CafeF trong toàn bộ cửa sổ `hours` gần nhất."""
    logger.info("POST /crawl/cafef hours=%.1f", hours)
    return JSONResponse(content=_serialize_stats(run_cafef_pipeline(hours)))


def _fetch_hnx_pdf_url(article_id: str) -> str | None:
    """Wrapper tạo fresh requests.Session cho HNX attach endpoint."""
    import requests as _requests
    from app.config import HTTP_TIMEOUT

    session = _requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        "Referer": "https://www.hnx.vn/",
    })
    try:
        return hnx_fetcher.fetch_hnx_pdf_url(session, article_id)
    finally:
        session.close()


def _serialize_stats(stats: dict) -> dict:
    """Chuyển đổi datetime thành string nếu cần (cho JSON response)."""
    result = {}
    for k, v in stats.items():
        if hasattr(v, "isoformat"):
            result[k] = v.isoformat()
        else:
            result[k] = v
    return result
