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

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def init_db() -> None:
    """Tạo bảng nếu chưa tồn tại. Gọi 1 lần lúc app khởi động."""
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(_CREATE_TABLE_SQL)
        conn.commit()
    logger.info("DB initialised (table trading_changes ready)")


def insert_records(records: list[dict[str, Any]]) -> int:
    """
    Lưu danh sách bản ghi vào bảng.
    Mỗi dict cần có các key:
        source, source_article_id, title, published_at,
        pdf_url, stock_code, organization_name, reason
    Trả về số dòng đã insert thực sự.
    """
    if not records:
        return 0

    _INSERT_SQL = """
    INSERT INTO trading_changes
        (source, source_article_id, title, published_at,
         pdf_url, stock_code, organization_name, reason)
    VALUES
        (%(source)s, %(source_article_id)s, %(title)s, %(published_at)s,
         %(pdf_url)s, %(stock_code)s, %(organization_name)s, %(reason)s)
    """

    inserted = 0
    for rec in records:
        try:
            with psycopg.connect(DATABASE_URL) as conn:
                with conn.cursor() as cur:
                    cur.execute(_INSERT_SQL, rec)
                conn.commit()
            inserted += 1
        except Exception as exc:
            logger.error("DB insert error for %s/%s: %s",
                         rec.get("source"), rec.get("source_article_id"), exc)

    logger.info("Inserted %d/%d records into DB", inserted, len(records))
    return inserted
