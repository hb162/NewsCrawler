"""
HSX list parser: JSON API response → list[{news_id, title, posted_at}]

Response thực tế (xác nhận qua DevTools):
{
  "data": {
    "list": [
      {
        "id": 2470184,
        "title": "...",
        "postedDate": 1781289402   # unix seconds (không phải ms)
      },
      ...
    ]
  }
}
Lưu ý: postedDate là Unix timestamp *seconds*, biểu diễn theo giờ UTC.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import pytz

logger = logging.getLogger(__name__)

_VN_TZ = pytz.timezone("Asia/Ho_Chi_Minh")


def parse_hsx_list(data: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Parse JSON response của HSX news/cate API.
    Trả về list[{news_id: str, title: str, posted_at: datetime (aware, VN tz)}].
    """
    # Cấu trúc thực tế: data["data"]["list"]
    inner = data.get("data") or {}
    if isinstance(inner, dict):
        items = inner.get("list") or inner.get("items") or []
    elif isinstance(inner, list):
        items = inner
    else:
        items = []

    # Fallback các key khác nếu cấu trúc khác
    if not items:
        for key in ("list", "items", "pageData", "newsData"):
            candidate = data.get(key)
            if isinstance(candidate, list):
                items = candidate
                break

    results: list[dict[str, Any]] = []
    for item in items:
        news_id = str(item.get("id") or item.get("newsId") or "")
        title = item.get("title") or item.get("name") or ""
        posted_raw = (
            item.get("postedDate")
            or item.get("publishedDate")
            or item.get("publishDate")
            or item.get("publishFrom")
        )

        if not news_id or not title:
            continue

        posted_at = _parse_posted_date(posted_raw)

        results.append({
            "news_id": news_id,
            "title": title,
            "posted_at": posted_at,
        })

    return results


def _parse_posted_date(raw: Any) -> datetime | None:
    """
    Chuyển đổi postedDate của HSX sang datetime aware (VN tz).
    Giá trị thực tế: unix seconds (int, ~1.78e9 tức là năm 2026).
    """
    if raw is None:
        return None

    if isinstance(raw, (int, float)):
        # Phân biệt seconds vs milliseconds: nếu > 1e12 thì là ms
        ts = raw / 1000 if raw > 1e12 else raw
        utc_dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        return utc_dt.astimezone(_VN_TZ)

    if isinstance(raw, str):
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                naive = datetime.strptime(raw.strip(), fmt)
                return _VN_TZ.localize(naive)
            except ValueError:
                continue

    return None
