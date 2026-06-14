"""
HSX fetcher: gọi API HSX JSON, lọc theo cửa sổ thời gian.

API danh sách (xác nhận qua DevTools):
  GET https://api.hsx.vn/n/api/v1/1/news/cate
  Params: aliasCate=tin-tuc/giao-dich-ky-quy, startDate=YYYY-MM-DD, endDate=YYYY-MM-DD,
          pageIndex, pageSize
  Header bắt buộc: type: HJ2HNS3SKICV4FNE
  Response: {"data": {"list": [{id, title, postedDate, ...}]}}

API file đính kèm (xác nhận qua DevTools):
  GET https://api.hsx.vn/m/api/v1/1/mediafiles/1/{news_id}?pageIndex=1&pageSize=100&year=0
  Response: {"data": {"list": [{"filePath": "~/Uploads/...", "fileType": ".pdf"}]}}
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta

import requests
import pytz

from app.config import HTTP_TIMEOUT
from app.parsers.hsx_list import parse_hsx_list
from app.parsers.hsx_pdf import build_hsx_pdf_url

logger = logging.getLogger(__name__)

_VN_TZ = pytz.timezone("Asia/Ho_Chi_Minh")

# ---------------------------------------------------------------------------
# HSX API endpoints (xác nhận qua DevTools)
# ---------------------------------------------------------------------------
_NEWS_CATE_URL = "https://api.hsx.vn/n/api/v1/1/news/cate"
_MEDIAFILES_URL_TPL = "https://api.hsx.vn/m/api/v1/1/mediafiles/1/{news_id}"
_ALIAS_CATE = "tin-tuc/giao-dich-ky-quy"
_PAGE_SIZE = 30

_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.hsx.vn/",
    "Accept": "application/json, text/plain, */*",
    "type": "HJ2HNS3SKICV4FNE",   # header bắt buộc của HSX API
    "Origin": "https://www.hsx.vn",
}


def _now_vn() -> datetime:
    return datetime.now(tz=_VN_TZ)


def fetch_hsx_articles(window_hours: float) -> list[dict]:
    """
    Crawl danh sách bài từ HSX category "giao-dich-ky-quy" trong `window_hours` giờ gần nhất.
    Tự dừng phân trang khi gặp bài cũ hơn cửa sổ.
    Trả về list[{news_id, title, posted_at}].
    """
    now_vn = _now_vn()
    cutoff = now_vn - timedelta(hours=window_hours)

    # API dùng format YYYY-MM-DD, cộng buffer 1 ngày để không bỏ sót
    start_date = (cutoff - timedelta(days=1)).strftime("%Y-%m-%d")
    end_date = (now_vn + timedelta(days=1)).strftime("%Y-%m-%d")

    logger.info(
        "HSX: crawling since %s (%.1f hours), startDate=%s endDate=%s",
        cutoff.isoformat(), window_hours, start_date, end_date,
    )

    articles: list[dict] = []
    page = 1
    stop = False

    session = requests.Session()
    session.headers.update(_DEFAULT_HEADERS)

    try:
        while not stop:
            data = _fetch_news_page(session, page, start_date, end_date)
            if data is None:
                break

            rows = parse_hsx_list(data)
            if not rows:
                logger.debug("HSX page %d: no rows, stopping", page)
                break

            for row in rows:
                posted_at: datetime | None = row.get("posted_at")
                if posted_at and posted_at < cutoff:
                    logger.debug(
                        "HSX page %d: row date %s < cutoff, stopping",
                        page, posted_at.isoformat(),
                    )
                    stop = True
                    break
                articles.append(row)

            logger.info(
                "HSX page %d: %d rows fetched (total so far: %d)",
                page, len(rows), len(articles),
            )
            page += 1

            if not stop:
                time.sleep(0.3)
    finally:
        session.close()

    logger.info("HSX: %d articles found in window", len(articles))
    return articles


def fetch_hsx_pdf_url(news_id: str) -> str | None:
    """
    Lấy URL PDF cho bài viết HSX theo news_id.
    Endpoint: GET /m/api/v1/1/mediafiles/1/{news_id}?pageIndex=1&pageSize=100&year=0
    Trả về URL string hoặc None.
    """
    url = _MEDIAFILES_URL_TPL.format(news_id=news_id)
    try:
        resp = requests.get(
            url,
            params={"pageIndex": 1, "pageSize": 100, "year": 0},
            headers=_DEFAULT_HEADERS,
            timeout=HTTP_TIMEOUT,
            allow_redirects=True,
        )
        resp.raise_for_status()
        data = resp.json()

        files = data.get("data", {}).get("list", [])
        for f in files:
            file_type = (f.get("fileType") or "").lower()
            file_path = f.get("filePath") or ""
            if file_type == ".pdf" or file_path.lower().endswith(".pdf"):
                return build_hsx_pdf_url(file_path)

        logger.warning("HSX: no PDF found in mediafiles for news_id=%s", news_id)
        return None
    except Exception as exc:
        logger.error("HSX: error fetching mediafiles for news_id=%s: %s", news_id, exc)
        return None


def fetch_pdf_bytes(url: str) -> bytes | None:
    """Tải PDF từ URL, trả về bytes hoặc None nếu lỗi."""
    try:
        resp = requests.get(
            url,
            headers=_DEFAULT_HEADERS,
            timeout=HTTP_TIMEOUT,
            allow_redirects=True,
        )
        resp.raise_for_status()
        return resp.content
    except Exception as exc:
        logger.error("fetch_pdf_bytes (hsx): error downloading %s: %s", url, exc)
        return None


def _fetch_news_page(session: requests.Session, page: int, start_date: str, end_date: str) -> dict | None:
    """GET JSON trang danh sách HSX."""
    try:
        resp = session.get(
            _NEWS_CATE_URL,
            params={
                "aliasCate": _ALIAS_CATE,
                "startDate": start_date,
                "endDate": end_date,
                "pageIndex": page,
                "pageSize": _PAGE_SIZE,
            },
            timeout=HTTP_TIMEOUT,
            allow_redirects=True,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        logger.error("HSX: error fetching news page %d: %s", page, exc)
        return None
