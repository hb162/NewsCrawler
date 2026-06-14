"""
LLM classification parser: raw LLM text → list[{index, should_crawl, reason}]
Đây là pure-parser không gọi LLM — chỉ validate & normalize kết quả đã parse.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def parse_classify_response(raw: list[Any]) -> list[dict[str, Any]]:
    """
    Nhận kết quả đã JSON-parsed từ llm.classify_titles(),
    validate và trả về list[{index: int, should_crawl: bool, reason: str}].
    Bỏ qua phần tử không hợp lệ.
    """
    results: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            logger.warning("parse_classify_response: skip non-dict item: %s", item)
            continue

        try:
            index = int(item["index"])
            should_crawl = bool(item["should_crawl"])
            reason = str(item.get("reason") or "")
            results.append({"index": index, "should_crawl": should_crawl, "reason": reason})
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning("parse_classify_response: invalid item %s: %s", item, exc)

    return results
