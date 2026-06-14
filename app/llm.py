"""
Anthropic client wrapper.
Cung cấp hai hàm gọi LLM:
  - classify_titles()   : phân loại lô tiêu đề
  - extract_from_pdf()  : OCR + trích xuất thông tin từ PDF bytes
"""
from __future__ import annotations

import base64
import json
import logging
import time
from typing import Any

import anthropic

from app.config import (
    ANTHROPIC_API_KEY,
    ANTHROPIC_MODEL,
    LLM_MAX_RETRIES,
)

logger = logging.getLogger(__name__)

_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_CLASSIFY_SYSTEM = """
Bạn là chuyên gia phân tích tin tức thị trường chứng khoán Việt Nam.
Nhiệm vụ: quyết định xem mỗi tiêu đề có liên quan đến **thay đổi dạng giao dịch**
của cổ phiếu/chứng khoán hay không.

Định nghĩa **rộng** của "thay đổi dạng giao dịch":
  - Đưa vào / ra khỏi diện kiểm soát, cảnh báo, hạn chế giao dịch
  - Cho phép / đình chỉ / thu hồi giao dịch ký quỹ (margin)
  - Thay đổi biên độ dao động giá
  - Đình chỉ hoặc tạm ngừng giao dịch
  - Chuyển sang đăng ký giao dịch / hủy niêm yết
  - Quyết định / thông báo liên quan điều kiện giao dịch

Ví dụ LIÊN QUAN (should_crawl=true):
  - "Quyết định đưa cổ phiếu ABC vào diện kiểm soát"
  - "Thông báo cho vay giao dịch ký quỹ đối với cổ phiếu XYZ"
  - "Đình chỉ giao dịch chứng chỉ quỹ DEF"
  - "Đưa ra khỏi diện hạn chế giao dịch"

Ví dụ KHÔNG liên quan (should_crawl=false):
  - "Kết quả kinh doanh quý 2/2024"
  - "Thông báo họp Đại hội đồng cổ đông"
  - "Công bố thông tin về phát hành cổ phiếu"
  - "Báo cáo tài chính năm 2023"

Trả về ĐÚNG định dạng JSON sau (array), không có text thừa:
[
  {"index": <số nguyên>, "should_crawl": <true|false>, "reason": "<lý do ngắn gọn>"},
  ...
]
"""

_EXTRACT_SYSTEM = """
Bạn là chuyên gia phân tích văn bản hành chính chứng khoán Việt Nam.
Nhiệm vụ: đọc nội dung văn bản/thông báo và trích xuất TẤT CẢ mã chứng khoán
bị ảnh hưởng bởi quyết định thay đổi dạng giao dịch trong văn bản.

Quy tắc:
  - Một văn bản có thể chứa NHIỀU mã cổ phiếu → trả về danh sách
  - Nếu không tìm thấy mã nào rõ ràng → trả về danh sách rỗng []
  - stock_code: mã chứng khoán viết HOA (vd: "ABC", "VNM"), nếu không tìm thấy để ""
  - organization_name: tên đầy đủ của tổ chức/công ty (lấy nguyên văn từ tài liệu)
  - reason: lý do / loại thay đổi dạng giao dịch được áp dụng

Trả về ĐÚNG định dạng JSON sau (array), không có text thừa:
[
  {"stock_code": "<MÃ>", "organization_name": "<Tên tổ chức>", "reason": "<lý do>"},
  ...
]
"""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _call_with_retry(messages: list[dict], system: str, max_tokens: int = 4096) -> str:
    """Gọi Anthropic với retry, trả về content text."""
    last_exc: Exception | None = None
    for attempt in range(1, LLM_MAX_RETRIES + 1):
        try:
            response = _client.messages.create(
                model=ANTHROPIC_MODEL,
                max_tokens=max_tokens,
                system=system,
                messages=messages,
            )
            # Cảnh báo nếu bị truncate do hết token
            stop_reason = response.stop_reason
            if stop_reason == "max_tokens":
                logger.warning(
                    "LLM response truncated (stop_reason=max_tokens, max_tokens=%d). "
                    "JSON có thể bị cắt — sẽ cố parse partial.",
                    max_tokens,
                )
            return response.content[0].text
        except Exception as exc:
            last_exc = exc
            wait = 2 ** attempt
            logger.warning("LLM call failed (attempt %d/%d): %s — retry in %ds",
                           attempt, LLM_MAX_RETRIES, exc, wait)
            time.sleep(wait)
    raise RuntimeError(f"LLM call failed after {LLM_MAX_RETRIES} retries") from last_exc


def _parse_json_response(text: str) -> Any:
    """
    Parse JSON từ response LLM.
    - Bỏ markdown fence nếu có.
    - Nếu JSON array bị cắt giữa chừng (truncated by max_tokens),
      cố gắng recover bằng cách đóng array tại object hoàn chỉnh cuối cùng.
    """
    text = text.strip()

    # Bỏ ```json ... ``` fence
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        text = text.strip()

    # Parse thẳng nếu hợp lệ
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Fallback: nếu là array bị truncate, cắt tại "}" cuối cùng hoàn chỉnh rồi đóng "]"
    if text.startswith("["):
        last_closing = text.rfind("}")
        if last_closing != -1:
            recovered = text[: last_closing + 1] + "\n]"
            try:
                result = json.loads(recovered)
                logger.warning(
                    "_parse_json_response: recovered truncated JSON array, "
                    "got %d items (original text length=%d)",
                    len(result) if isinstance(result, list) else "?",
                    len(text),
                )
                return result
            except json.JSONDecodeError as exc:
                logger.error("_parse_json_response: recovery also failed: %s", exc)

    raise ValueError(f"Cannot parse LLM response as JSON (first 200 chars): {text[:200]}")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def classify_titles(titles: list[str]) -> list[dict[str, Any]]:
    """
    Gửi danh sách tiêu đề cho LLM phân loại.
    Trả về list[{index, should_crawl, reason}].
    Nếu LLM trả JSON sai, raise ValueError.
    """
    numbered = "\n".join(f"{i}. {t}" for i, t in enumerate(titles))
    messages = [{"role": "user", "content": f"Phân loại các tiêu đề sau:\n\n{numbered}"}]

    raw = _call_with_retry(messages, _CLASSIFY_SYSTEM)
    logger.debug("classify_titles raw response: %s", raw[:300])

    result = _parse_json_response(raw)
    if not isinstance(result, list):
        raise ValueError(f"Expected JSON array, got: {type(result)}")
    return result


def extract_from_pdf(pdf_bytes: bytes) -> list[dict[str, Any]]:
    """
    Gửi PDF bytes cho LLM để OCR + trích xuất.
    Trả về list[{stock_code, organization_name, reason}].
    """
    pdf_b64 = base64.standard_b64encode(pdf_bytes).decode()

    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "document",
                    "source": {
                        "type": "base64",
                        "media_type": "application/pdf",
                        "data": pdf_b64,
                    },
                },
                {
                    "type": "text",
                    "text": (
                        "Đọc văn bản trên và trích xuất tất cả mã chứng khoán "
                        "bị ảnh hưởng bởi quyết định thay đổi dạng giao dịch. "
                        "Trả về JSON array theo đúng format đã hướng dẫn."
                    ),
                },
            ],
        }
    ]

    raw = _call_with_retry(messages, _EXTRACT_SYSTEM, max_tokens=8192)
    logger.debug("extract_from_pdf raw response: %s", raw[:300])

    result = _parse_json_response(raw)
    if not isinstance(result, list):
        raise ValueError(f"Expected JSON array, got: {type(result)}")
    return result
