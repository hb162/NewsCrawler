"""
Pipeline orchestrator: điều phối 5 bước chung cho cả HNX và HSX.
...
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Callable

import httpx

from app.config import CLASSIFY_BATCH_SIZE
from app.db import insert_records
from app.llm import classify_titles, extract_from_pdf
from app.parsers.llm_classify import parse_classify_response
from app.parsers.llm_extract import parse_extract_response

logger = logging.getLogger(__name__)


def run_pipeline(
    source: str,
    window_hours: float,
    fetch_articles: Callable[[], list[dict]],
    fetch_pdf_url: Callable[[str], str | None],
    fetch_pdf_bytes: Callable[[str], bytes | None],
    article_id_key: str,
    published_at_key: str,
) -> dict[str, Any]:
    """
    Chạy pipeline chung cho một nguồn.

    Args:
        source: 'hnx' hoặc 'hsx'
        window_hours: cửa sổ thời gian (giờ)
        fetch_articles: hàm trả list[dict] bài viết
        fetch_pdf_url: hàm (article_id) → URL PDF
        fetch_pdf_bytes: hàm (url) → bytes
        article_id_key: key trong dict bài để lấy article_id
        published_at_key: key trong dict bài để lấy published_at (datetime)

    Returns:
        dict tóm tắt kết quả
    """
    stats = {
        "source": source,
        "window_hours": window_hours,
        "titles_found": 0,
        "selected_by_llm": 0,
        "pdfs_processed": 0,
        "records_inserted": 0,
        "errors_count": 0,
    }

    # -----------------------------------------------------------------------
    # Bước 1: Crawl danh sách
    # -----------------------------------------------------------------------
    try:
        articles = fetch_articles()
    except Exception as exc:
        logger.error("[%s] fetch_articles failed: %s", source, exc)
        stats["errors_count"] += 1
        return stats

    stats["titles_found"] = len(articles)
    if not articles:
        logger.info("[%s] No articles found, done.", source)
        return stats

    # -----------------------------------------------------------------------
    # Bước 2: LLM phân loại theo lô
    # -----------------------------------------------------------------------
    selected_articles: list[dict] = []

    for batch_start in range(0, len(articles), CLASSIFY_BATCH_SIZE):
        batch = articles[batch_start: batch_start + CLASSIFY_BATCH_SIZE]
        titles = [a["title"] for a in batch]

        try:
            raw_classify = classify_titles(titles)
            classify_results = parse_classify_response(raw_classify)
        except Exception as exc:
            logger.error("[%s] LLM classify failed for batch starting at %d: %s",
                         source, batch_start, exc)
            stats["errors_count"] += 1
            continue

        for item in classify_results:
            idx = item["index"]
            if 0 <= idx < len(batch) and item["should_crawl"]:
                logger.debug("[%s] Selected: '%s' (reason: %s)",
                             source, batch[idx]["title"], item["reason"])
                selected_articles.append(batch[idx])

    stats["selected_by_llm"] = len(selected_articles)
    logger.info("[%s] LLM selected %d/%d articles", source, len(selected_articles), len(articles))

    if not selected_articles:
        return stats

    # -----------------------------------------------------------------------
    # Bước 3 + 4 + 5: Với mỗi bài được chọn → PDF → OCR → lưu
    # -----------------------------------------------------------------------
    all_records: list[dict] = []

    for article in selected_articles:
        art_id = str(article.get(article_id_key) or "")
        title = article.get("title", "")
        published_at: datetime | None = article.get(published_at_key)

        # Bước 3: Lấy PDF URL
        try:
            pdf_url = fetch_pdf_url(art_id)
        except Exception as exc:
            logger.error("[%s] fetch_pdf_url failed for article_id=%s: %s", source, art_id, exc)
            stats["errors_count"] += 1
            continue

        if not pdf_url:
            logger.warning("[%s] No PDF URL for article_id=%s, skipping", source, art_id)
            stats["errors_count"] += 1
            continue

        # Bước 4a: Tải PDF
        try:
            pdf_bytes = fetch_pdf_bytes(pdf_url)
        except Exception as exc:
            logger.error("[%s] fetch_pdf_bytes failed for %s: %s", source, pdf_url, exc)
            stats["errors_count"] += 1
            continue

        if not pdf_bytes:
            logger.warning("[%s] Empty PDF for article_id=%s (%s)", source, art_id, pdf_url)
            stats["errors_count"] += 1
            continue

        # Bước 4b: LLM OCR + trích xuất
        try:
            raw_extract = extract_from_pdf(pdf_bytes)
            extract_results = parse_extract_response(raw_extract)
        except Exception as exc:
            logger.error("[%s] LLM extract failed for article_id=%s: %s", source, art_id, exc)
            stats["errors_count"] += 1
            continue

        stats["pdfs_processed"] += 1

        if not extract_results:
            logger.warning("[%s] LLM returned no entities for article_id=%s", source, art_id)
            # Không increment error — bài có thể không chứa mã nào
            continue

        # Bước 5: Chuẩn bị record DB
        for entity in extract_results:
            all_records.append({
                "source": source,
                "source_article_id": art_id,
                "title": title,
                "published_at": published_at,
                "pdf_url": pdf_url,
                "stock_code": entity["stock_code"],
                "organization_name": entity["organization_name"],
                "reason": entity["reason"],
            })

    # Lưu tất cả vào DB
    if all_records:
        try:
            inserted = insert_records(all_records)
            stats["records_inserted"] = inserted
        except Exception as exc:
            logger.error("[%s] insert_records failed: %s", source, exc)
            stats["errors_count"] += 1

    logger.info(
        "[%s] Done. titles=%d selected=%d pdfs=%d records=%d errors=%d",
        source,
        stats["titles_found"],
        stats["selected_by_llm"],
        stats["pdfs_processed"],
        stats["records_inserted"],
        stats["errors_count"],
    )
    return stats
