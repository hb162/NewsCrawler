"""
DB layer: init_db() tạo bảng, insert_records() lưu danh sách bản ghi.
Dùng psycopg3 thuần (không SQLAlchemy).
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import psycopg

from app.config import DATABASE_URL

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------
_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS trading_changes (
    id                BIGSERIAL PRIMARY KEY,
    source            VARCHAR(10)  NOT NULL,        -- 'hnx' | 'hsx'
    source_article_id VARCHAR(64)  NOT NULL,
    title             TEXT         NOT NULL,
    published_at      TIMESTAMPTZ,
    pdf_url           TEXT,
    stock_code        VARCHAR(20)  NOT NULL,
    organization_name TEXT,
    reason            TEXT,
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
"""

_CREATE_CAFEF_SQL = """
CREATE TABLE IF NOT EXISTS cafef_articles (
    id                BIGSERIAL PRIMARY KEY,
    source_article_id VARCHAR(64) NOT NULL,
    url               TEXT NOT NULL,
    title             TEXT NOT NULL,
    body              TEXT NOT NULL,
    published_at      TIMESTAMPTZ NOT NULL,
    stock_codes       TEXT[] NOT NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (cardinality(stock_codes) > 0)
);
"""

_INSERT_TRADING_CHANGE_SQL = """
INSERT INTO trading_changes
    (source, source_article_id, title, published_at,
     pdf_url, stock_code, organization_name, reason)
VALUES
    (%(source)s, %(source_article_id)s, %(title)s, %(published_at)s,
     %(pdf_url)s, %(stock_code)s, %(organization_name)s, %(reason)s)
"""

_INSERT_CAFEF_SQL = """
INSERT INTO cafef_articles
    (source_article_id, url, title, body, published_at, stock_codes)
VALUES
    (%(source_article_id)s, %(url)s, %(title)s, %(body)s,
     %(published_at)s, %(stock_codes)s)
"""

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def init_db() -> None:
    """Tạo các bảng ứng dụng nếu chưa tồn tại. Gọi lúc app khởi động."""
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(_CREATE_TABLE_SQL)
            cur.execute(_CREATE_CAFEF_SQL)
        conn.commit()
    logger.info("DB initialised (tables trading_changes, cafef_articles ready)")


def insert_records(records: list[dict[str, Any]]) -> int:
    """Lưu các thay đổi giao dịch HNX/HSX, resilient theo từng row."""
    if not records:
        return 0

    inserted = 0
    for rec in records:
        try:
            with psycopg.connect(DATABASE_URL) as conn:
                with conn.cursor() as cur:
                    cur.execute(_INSERT_TRADING_CHANGE_SQL, rec)
                conn.commit()
            inserted += 1
        except Exception as exc:
            logger.error("DB insert error for %s/%s: %s",
                         rec.get("source"), rec.get("source_article_id"), exc)

    logger.info("Inserted %d/%d records into DB", inserted, len(records))
    return inserted


def insert_cafef_articles(records: list[dict[str, Any]]) -> int:
    """Lưu bài CafeF hợp lệ, tiếp tục nếu một row insert thất bại."""
    if not records:
        return 0

    inserted = 0
    for rec in records:
        try:
            with psycopg.connect(DATABASE_URL) as conn:
                with conn.cursor() as cur:
                    cur.execute(_INSERT_CAFEF_SQL, rec)
                conn.commit()
            inserted += 1
        except Exception as exc:
            logger.error(
                "DB insert error for cafef/%s: %s",
                rec.get("source_article_id"),
                exc,
            )

    logger.info("Inserted %d/%d CafeF articles into DB", inserted, len(records))
    return inserted
