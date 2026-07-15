"""Pure parser for CafeF article detail HTML."""
from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any
from urllib.parse import parse_qs, urlsplit

from bs4 import BeautifulSoup
import pytz

logger = logging.getLogger(__name__)

_VN_TZ = pytz.timezone("Asia/Ho_Chi_Minh")
_STOCK_LINK_RE = re.compile(
    r"(?:https?://cafef\.vn)?/du-lieu/(?:hose|hnx|upcom)/([a-z0-9]{3})-",
    re.IGNORECASE,
)
_STOCK_CODE_RE = re.compile(r"^[A-Z0-9]{3}$")
_WIDGET_TITLE_RE = re.compile(r"^([A-Z0-9]{3}):")
_CANDIDATE_SELECTOR = "p, h2, h3, blockquote, li"
_NOISE_SELECTORS = (
    "script", "style", "iframe", "figure", "figcaption",
    ".VCSortableInPreviewMode", ".PhotoCMS_Caption", ".tindnd",
    "#listNewsInContent", "[data-marked-zoneid]", ".chisochungkhoan",
    ".h-show-pc", ".h-show-mobile", "[class*='banner']", "[id^='admzone']",
)


def parse_cafef_article(
    html: str,
    article_id: str,
    url: str,
) -> dict[str, Any] | None:
    """Parse title, authoritative date, clean body and structured stock codes."""
    soup = BeautifulSoup(html, "lxml")
    title_node = (
        soup.select_one("h1[data-role='title']")
        or soup.select_one("h1.title")
        or soup.find("h1")
    )
    title = _normalize(title_node.get_text(" ", strip=True)) if title_node else ""
    body = _extract_body(soup)
    if not title or not body:
        logger.warning("CafeF parse failed: missing title/body for article_id=%s", article_id)
        return None

    return {
        "source_article_id": str(article_id),
        "url": url,
        "title": title,
        "published_at": _extract_published_at(soup),
        "body": body,
        "stock_codes": _extract_stock_codes(soup),
    }


def _extract_published_at(soup: BeautifulSoup) -> datetime | None:
    node = soup.select_one("[data-role='publishdate']")
    if node is None:
        return None

    raw_datetime = str(node.get("datetime") or "").strip()
    if raw_datetime:
        parsed = _parse_datetime(raw_datetime)
        if parsed is not None:
            return parsed

    visible = _normalize(node.get_text(" ", strip=True))
    return _parse_datetime(visible)


def _parse_datetime(raw: str) -> datetime | None:
    value = raw.strip()
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return _localize(parsed)
    except ValueError:
        pass

    for fmt in (
        "%d-%m-%Y - %H:%M",
        "%d-%m-%Y - %I:%M %p",
        "%d/%m/%Y %H:%M",
        "%d/%m/%Y - %H:%M",
    ):
        try:
            return _VN_TZ.localize(datetime.strptime(value, fmt))
        except ValueError:
            continue
    logger.debug("CafeF article: cannot parse publish date %r", raw)
    return None


def _localize(value: datetime) -> datetime:
    if value.tzinfo is None:
        return _VN_TZ.localize(value)
    return value.astimezone(_VN_TZ)


def _extract_body(soup: BeautifulSoup) -> str:
    source_root = soup.select_one("[data-role='content']")
    if source_root is None:
        return ""

    fragment = BeautifulSoup(str(source_root), "lxml")
    root = fragment.select_one("[data-role='content']")
    if root is None:
        return ""

    for selector in _NOISE_SELECTORS:
        for node in root.select(selector):
            node.decompose()

    paragraphs: list[str] = []
    seen_text: set[str] = set()
    for node in root.select(_CANDIDATE_SELECTOR):
        if node.select_one(_CANDIDATE_SELECTOR) is not None:
            continue
        text = _normalize(node.get_text(" ", strip=True))
        if text and text not in seen_text:
            seen_text.add(text)
            paragraphs.append(text)

    sapo_node = soup.select_one("[data-role='sapo']")
    sapo = _normalize(sapo_node.get_text(" ", strip=True)) if sapo_node else ""
    if sapo and (not paragraphs or sapo != paragraphs[0]):
        paragraphs.insert(0, sapo)

    return "\n".join(paragraphs)


def _extract_stock_codes(soup: BeautifulSoup) -> list[str]:
    codes: list[str] = []
    seen: set[str] = set()

    def add(raw: str) -> bool:
        code = raw.strip().upper()
        if not _STOCK_CODE_RE.fullmatch(code):
            return False
        if code not in seen:
            seen.add(code)
            codes.append(code)
        return True

    for link in soup.select("a[href]"):
        match = _STOCK_LINK_RE.search(str(link.get("href") or ""))
        if match:
            add(match.group(1))

    for widget in soup.select(".chisochungkhoan"):
        found_in_iframe = False
        for iframe in widget.select("iframe[src*='symbol=']"):
            params = parse_qs(urlsplit(str(iframe.get("src") or "")).query)
            for value in params.get("symbol", []):
                found_in_iframe = add(value) or found_in_iframe
        if not found_in_iframe:
            heading = widget.select_one("h2.title_box")
            heading_text = _normalize(heading.get_text(" ", strip=True)) if heading else ""
            match = _WIDGET_TITLE_RE.match(heading_text.upper())
            if match:
                add(match.group(1))

    return codes


def _normalize(value: str) -> str:
    return " ".join(value.split())