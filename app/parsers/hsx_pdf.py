"""
HSX PDF URL builder: filePath → URL staticfile.hsx.vn
...
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_STATIC_BASE = "https://staticfile.hsx.vn/"


def build_hsx_pdf_url(file_path: str) -> str | None:
    """
    Ghép URL PDF từ filePath trả về bởi HSX mediafiles API.
    Trả về URL đầy đủ, hoặc None nếu không thể xử lý.
    """
    if not file_path:
        return None

    path = file_path.strip()

    # ~/Uploads/... → Uploads/...
    if path.startswith("~/"):
        path = path[2:]
    elif path.startswith("/"):
        path = path.lstrip("/")

    url = _STATIC_BASE + path
    logger.debug("build_hsx_pdf_url: %s → %s", file_path, url)
    return url
