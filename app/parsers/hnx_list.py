"""
HNX list parser: HTML bảng 6 cột → list[{date, stock_code, title, article_id}]

Cột thứ tự (1-indexed):
  1: STT
  2: Ngày đăng tin  (dd/mm/yyyy HH:MM)
  3: Mã CK
  4: Tên TCPH
  5: Tiêu đề — onclick="funcViewDetailArticlesByID(ID,1)"
  6: File đính kèm — onclick="funcShowFileAttach(ID,1)"

Article ID lấy từ: onclick="funcViewDetailArticlesByID(619742,1)"
"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any

from bs4 import BeautifulSoup
import pytz

logger = logging.getLogger(__name__)

_VN_TZ = pytz.timezone("Asia/Ho_Chi_Minh")

# Regex lấy article_id từ onclick="funcViewDetailArticlesByID(619742,1)"
_ARTICLE_ID_RE = re.compile(r'funcViewDetailArticlesByID\((\d+),')


def parse_hnx_list(html: str) -> list[dict[str, Any]]:
    """
    Parse HTML response từ endpoint NextPageTCPHUpCoM.
    Trả về list[{date, stock_code, title, article_id}].
    """
    soup = BeautifulSoup(html, "lxml")

    table = soup.find("table")
    if not table:
        logger.warning("parse_hnx_list: no <table> found in HTML")
        return []

    rows = table.find_all("tr")
    results: list[dict[str, Any]] = []

    for row in rows:
        cols = row.find_all("td")
        if len(cols) < 5:
            continue  # skip header row hoặc row lỗi

        date_str  = cols[1].get_text(strip=True)
        stock_code = cols[2].get_text(strip=True)
        # cols[3] = Tên TCPH (bỏ qua)
        title_cell = cols[4]
        title = title_cell.get_text(strip=True)

        # Lấy article_id từ onclick của link tiêu đề
        article_id = ""
        link_tag = title_cell.find("a", onclick=True)
        if link_tag:
            m = _ARTICLE_ID_RE.search(link_tag["onclick"])
            if m:
                article_id = m.group(1)

        if not title or not article_id:
            continue

        dt = _parse_date(date_str)
        if dt is None:
            logger.debug("parse_hnx_list: cannot parse date '%s', skip row", date_str)
            continue

        results.append({
            "date": dt,
            "stock_code": stock_code,
            "title": title,
            "article_id": article_id,
        })

    return results


def _parse_date(s: str) -> datetime | None:
    """Parse chuỗi ngày từ HNX, luôn gắn timezone VN."""
    s = s.strip()
    for fmt in ("%d/%m/%Y %H:%M", "%d/%m/%Y", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            naive = datetime.strptime(s, fmt)
            return _VN_TZ.localize(naive)
        except ValueError:
            continue
    return None
