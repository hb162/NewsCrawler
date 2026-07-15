"""HTTP fetcher for CafeF category timeline and article details."""
from __future__ import annotations

import logging

import requests

from app.config import HTTP_TIMEOUT

logger = logging.getLogger(__name__)

_CATEGORY_URL = "https://cafef.vn/thi-truong-chung-khoan.chn"
_TIMELINE_URL_TEMPLATE = "https://cafef.vn/timelinelist/18831/{page}.chn"
_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8",
    "Referer": _CATEGORY_URL,
    "X-Requested-With": "XMLHttpRequest",
}


def fetch_cafef_list_page(session: requests.Session, page: int) -> str | None:
    """Fetch page 1 from the category and page 2+ from the timeline endpoint."""
    if page < 1:
        raise ValueError("CafeF page must be >= 1")

    url = _CATEGORY_URL if page == 1 else _TIMELINE_URL_TEMPLATE.format(page=page)
    try:
        response = session.get(url, headers=_DEFAULT_HEADERS, timeout=(5, HTTP_TIMEOUT))
        response.raise_for_status()
        logger.info("CafeF list page %d: HTTP %d", page, response.status_code)
        return response.text
    except requests.RequestException as exc:
        logger.error("CafeF list page %d failed: %s", page, exc)
        return None


def fetch_cafef_article(session: requests.Session, url: str) -> str | None:
    """Fetch one CafeF article without terminating the surrounding batch on error."""
    try:
        response = session.get(url, headers=_DEFAULT_HEADERS, timeout=(5, HTTP_TIMEOUT))
        response.raise_for_status()
        return response.text
    except requests.RequestException as exc:
        logger.error("CafeF article fetch failed for %s: %s", url, exc)
        return None