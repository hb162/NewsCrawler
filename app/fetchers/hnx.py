"""
HNX fetcher: gọi endpoint HNX, lọc theo cửa sổ thời gian, trả danh sách bài viết.

Endpoint danh sách "Tin từ Sở" (xác nhận qua DevTools):
  POST https://www.hnx.vn/ModuleArticles/ArticlesCPEtfs/NextPageTCPHUpCoM
  Form fields: pNumPage, pAction, pNhomTin, pTieuDeTin, pMaChungKhoan,
               pFromDate, pToDate, pOrderBy
  Header bắt buộc: X-Requested-With: XMLHttpRequest
  Response: HTML bảng 6 cột, article_id lấy từ onclick="funcViewDetailArticlesByID(ID,1)"

Endpoint file đính kèm (xác nhận qua DevTools):
  POST https://www.hnx.vn/ModuleArticles/ArticlesCPEtfs/ShowFileAttach
  Form fields: pArticleId, pIsUpCoM=1
  Response: HTML chứa link owa.hnx.vn
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta

import requests
import pytz

from app.config import HTTP_TIMEOUT
from app.parsers.hnx_list import parse_hnx_list
from app.parsers.hnx_attach import parse_hnx_attach

logger = logging.getLogger(__name__)

_VN_TZ = pytz.timezone("Asia/Ho_Chi_Minh")

# ---------------------------------------------------------------------------
# HNX endpoint constants (xác nhận qua DevTools)
# ---------------------------------------------------------------------------
_LIST_URL   = "https://www.hnx.vn/ModuleArticles/ArticlesCPEtfs/NextPageTCPHUpCoM"
_ATTACH_URL = "https://www.hnx.vn/ModuleArticles/ArticlesCPEtfs/ArticlesFileAttach"

_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.hnx.vn/thong-tin-cong-bo-up-hnx.html",
    "Origin": "https://www.hnx.vn",
    "X-Requested-With": "XMLHttpRequest",
    "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8",
}


def _now_vn() -> datetime:
    return datetime.now(tz=_VN_TZ)


def fetch_hnx_articles(window_hours: float) -> list[dict]:
    """
    Crawl danh sách bài từ HNX tab "Tin từ Sở" trong `window_hours` giờ gần nhất.
    Tự dừng phân trang khi gặp bài cũ hơn cửa sổ.
    Trả về list[{date, stock_code, title, article_id}].
    """
    cutoff = _now_vn() - timedelta(hours=window_hours)
    logger.info("HNX: crawling articles since %s (%.1f hours)", cutoff.isoformat(), window_hours)

    articles: list[dict] = []
    page = 1
    stop = False

    session = requests.Session()
    session.headers.update(_DEFAULT_HEADERS)

    try:
        while not stop:
            html = _fetch_list_page(session, page)
            if not html:
                break

            rows = parse_hnx_list(html)
            if not rows:
                logger.debug("HNX page %d: no rows, stopping", page)
                break

            for row in rows:
                row_date: datetime = row["date"]
                if row_date < cutoff:
                    logger.debug(
                        "HNX page %d: row date %s < cutoff, stopping pagination",
                        page, row_date.isoformat(),
                    )
                    stop = True
                    break
                articles.append(row)

            logger.info(
                "HNX page %d: %d rows fetched (total so far: %d)",
                page, len(rows), len(articles),
            )
            page += 1

            if not stop:
                time.sleep(0.3)
    finally:
        session.close()

    logger.info("HNX: %d articles found in window", len(articles))
    return articles


def fetch_hnx_pdf_url(session: requests.Session, article_id: str) -> str | None:
    """
    Lấy URL PDF đính kèm của bài viết HNX theo article_id.
    POST ShowFileAttach với pArticleId và pIsUpCoM=1.
    Trả về URL string hoặc None.
    """
    try:
        resp = session.post(
            _ATTACH_URL,
            data={"pArticlesID": article_id},
            timeout=HTTP_TIMEOUT,
            allow_redirects=True,
        )
        resp.raise_for_status()
        return parse_hnx_attach(resp.text)
    except Exception as exc:
        logger.error("HNX: error fetching attach for article %s: %s", article_id, exc)
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
        content_type = resp.headers.get("content-type", "")
        if "pdf" not in content_type.lower() and not url.lower().endswith(".pdf"):
            logger.warning(
                "fetch_pdf_bytes: unexpected content-type '%s' for %s",
                content_type, url,
            )
        return resp.content
    except Exception as exc:
        logger.error("fetch_pdf_bytes: error downloading %s: %s", url, exc)
        return None


def _fetch_list_page(session: requests.Session, page: int) -> str | None:
    """POST form-encoded để lấy HTML trang danh sách HNX."""
    try:
        resp = session.post(
            _LIST_URL,
            data={
                "pNumPage": str(page),
                "pAction": "0",
                "pNhomTin": "",
                "pTieuDeTin": "",
                "pMaChungKhoan": "",
                "pFromDate": "",
                "pToDate": "",
                "pOrderBy": "",
            },
            timeout=HTTP_TIMEOUT,
            allow_redirects=True,
        )
        resp.raise_for_status()
        return resp.text
    except Exception as exc:
        logger.error("HNX: error fetching list page %d: %s", page, exc)
        return None
