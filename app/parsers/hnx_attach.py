"""
HNX attach parser: HTML trang đính kèm → URL PDF trên owa.hnx.vn
"""
from __future__ import annotations

import logging
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

_OWA_HOST = "owa.hnx.vn"


def parse_hnx_attach(html: str) -> str | None:
    """
    Tìm link <a href="..."> trỏ tới host owa.hnx.vn chứa PDF.
    Trả về URL đầu tiên tìm được, hoặc None nếu không có.
    """
    soup = BeautifulSoup(html, "lxml")

    for a in soup.find_all("a", href=True):
        href: str = a["href"]
        if _OWA_HOST in href:
            # Đảm bảo có scheme
            if href.startswith("//"):
                href = "https:" + href
            elif not href.startswith("http"):
                href = "https://" + href
            logger.debug("parse_hnx_attach: found PDF URL %s", href)
            return href

    logger.warning("parse_hnx_attach: no owa.hnx.vn link found in HTML")
    return None
