"""Dedicated time-window pipeline for CafeF HTML articles."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

import pytz
import requests

from app.db import insert_cafef_articles
from app.fetchers.cafef import fetch_cafef_article, fetch_cafef_list_page
from app.parsers.cafef_article import parse_cafef_article
from app.parsers.cafef_list import parse_cafef_list

logger = logging.getLogger(__name__)

_VN_TZ = pytz.timezone("Asia/Ho_Chi_Minh")
_CLOCK_SKEW_TOLERANCE = timedelta(minutes=5)


def _now_vn() -> datetime:
    return datetime.now(tz=_VN_TZ)


def run_cafef_pipeline(window_hours: float) -> dict[str, Any]:
    """Crawl every CafeF article in the requested time window and persist valid rows."""
    if window_hours <= 0:
        raise ValueError("window_hours must be greater than zero")

    run_started_at = _now_vn()
    cutoff = run_started_at - timedelta(hours=window_hours)
    upper_bound = run_started_at + _CLOCK_SKEW_TOLERANCE
    stats: dict[str, Any] = {
        "source": "cafef",
        "window_hours": window_hours,
        "pages_fetched": 0,
        "articles_found": 0,
        "articles_parsed": 0,
        "articles_in_window": 0,
        "articles_with_codes": 0,
        "records_inserted": 0,
        "errors_count": 0,
    }
    records: list[dict[str, Any]] = []
    seen_article_ids: set[str] = set()
    last_hint: datetime | None = None
    order_is_descending = True
    page = 1
    stop_at_cutoff = False


    logger.info(
        "[cafef] Crawling since %s (%.1f hours)", cutoff.isoformat(), window_hours,
    )

    with requests.Session() as session:
        while not stop_at_cutoff:
            html = fetch_cafef_list_page(session, page)
            if html is None:
                stats["errors_count"] += 1
                break
            stats["pages_fetched"] += 1
            if not html.strip():
                break

            try:
                items = parse_cafef_list(html)
            except Exception as exc:
                logger.error("[cafef] Failed to parse list page %d: %s", page, exc)
                stats["errors_count"] += 1
                break
            if not items:
                break

            new_items = [
                item for item in items if item["article_id"] not in seen_article_ids
            ]
            if not new_items:
                logger.info("[cafef] Page %d has no new article IDs; stopping", page)
                break

            for item in new_items:
                article_id = item["article_id"]
                seen_article_ids.add(article_id)
                stats["articles_found"] += 1
                hint = item.get("published_at_hint")
                if hint is not None:
                    if last_hint is not None and hint > last_hint:
                        order_is_descending = False
                        logger.warning(
                            "[cafef] List order is not descending at article_id=%s; "
                            "cutoff early-stop disabled",
                            article_id,
                        )
                    last_hint = hint

                article_html = fetch_cafef_article(session, item["url"])
                if not article_html:
                    stats["errors_count"] += 1
                    continue

                try:
                    article = parse_cafef_article(article_html, article_id, item["url"])
                except Exception as exc:
                    logger.error("[cafef] Parse failed for article_id=%s: %s", article_id, exc)
                    stats["errors_count"] += 1
                    continue
                if article is None:
                    stats["errors_count"] += 1
                    continue

                stats["articles_parsed"] += 1
                published_at = article.get("published_at")
                if published_at is None or published_at.utcoffset() is None:
                    logger.warning("[cafef] Missing aware date for article_id=%s", article_id)
                    stats["errors_count"] += 1
                    continue

                if published_at < cutoff:
                    if order_is_descending and hint is not None and hint < cutoff:
                        stop_at_cutoff = True
                        logger.info(
                            "[cafef] Cutoff reached at article_id=%s (%s)",
                            article_id,
                            published_at.isoformat(),
                        )
                        break
                    continue
                if published_at > upper_bound:
                    continue

                stats["articles_in_window"] += 1
                if not article["stock_codes"]:
                    continue
                stats["articles_with_codes"] += 1
                records.append(article)

            logger.info(
                "[cafef] Page %d: %d items, %d new IDs (found=%d)",
                page,
                len(items),
                len(new_items),
                stats["articles_found"],
            )
            page += 1

    if records:
        try:
            inserted = insert_cafef_articles(records)
        except Exception as exc:
            logger.error("[cafef] DB batch insert failed: %s", exc)
            inserted = 0
        stats["records_inserted"] = inserted
        stats["errors_count"] += len(records) - inserted

    logger.info(
        "[cafef] Done. pages=%d found=%d parsed=%d in_window=%d "
        "with_codes=%d inserted=%d errors=%d",
        stats["pages_fetched"], stats["articles_found"],
        stats["articles_parsed"], stats["articles_in_window"],
        stats["articles_with_codes"], stats["records_inserted"],
        stats["errors_count"],
    )
    return stats