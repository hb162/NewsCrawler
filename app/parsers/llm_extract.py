"""
LLM extraction parser: raw LLM text → list[{stock_code, organization_name, reason}]
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def parse_extract_response(raw: list[Any]) -> list[dict[str, Any]]:
    """
    Nhận kết quả đã JSON-parsed từ llm.extract_from_pdf(),
    validate và trả về list[{stock_code, organization_name, reason}].
    """
    results: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            logger.warning("parse_extract_response: skip non-dict item: %s", item)
            continue

        stock_code = str(item.get("stock_code") or "").strip().upper()
        org_name = str(item.get("organization_name") or "").strip()
        reason = str(item.get("reason") or "").strip()

        results.append({
            "stock_code": stock_code,
            "organization_name": org_name,
            "reason": reason,
        })

    return results
