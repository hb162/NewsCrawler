"""Pure parser for CafeF category and timeline HTML fragments."""
from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup
import pytz

logger = logging.getLogger(__name__)

_BASE_URL = "https://cafef.vn"
_VN_TZ = pytz.timezone("Asia/Ho_Chi_Minh")
_ARTICLE_ID_RE = re.compile(r"-(\d+)\.chn$")


def parse_cafef_list(html: str) -> list[dict[str, Any]]:
    """Parse one CafeF category page/fragment, preserving DOM order."""
    soup = BeautifulSoup(html, "lxml")
    results: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for item in soup.select(".box-category-item"):
        link = item.select_one("h3 a[href]")
        if link is None:
            continue

        url = urljoin(_BASE_URL, str(link.get("href") or ""))
        parsed_url = urlsplit(url)
        match = _ARTICLE_ID_RE.search(parsed_url.path)
        title = _normalize(link.get_text(" ", strip=True))
        if (
            parsed_url.scheme != "https"
            or parsed_url.hostname not in {"cafef.vn", "www.cafef.vn"}
            or match is None
            or not title
        ):
            continue

        article_id = match.group(1)
        if article_id in seen_ids:
            continue
        seen_ids.add(article_id)

        time_node = item.select_one(".time[title]")
        hint = _parse_datetime(str(time_node.get("title") or "")) if time_node else None
        results.append({
            "article_id": article_id,
            "url": url,
            "list_title": title,
            "published_at_hint": hint,
        })

    return results


def _parse_datetime(raw: str) -> datetime | None:
    value = raw.strip()
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        logger.debug("CafeF list: cannot parse time hint %r", raw)
        return None

    if parsed.tzinfo is None:
        return _VN_TZ.localize(parsed)
    return parsed.astimezone(_VN_TZ)


def _normalize(value: str) -> str:
    return " ".join(value.split())