---
title: "CafeF crawler — crawl toàn văn bài viết liên quan cổ phiếu VN"
status: approved-design
created: 2026-07-14
related: docs/prd/news-crawler-hnx-hsx.md
---

# Brainstorm — CafeF crawler

## Problem statement
Bổ sung nguồn thứ 3 (CafeF, mục `thi-truong-chung-khoan.chn`) vào NewsCrawler:
crawl **toàn văn** bài viết mà **nhắc tới ≥1 mã cổ phiếu VN** (HOSE/HNX/UPCoM).
Khác bản chất HNX/HSX: nội dung là **bài báo HTML**, không phải PDF scan → không OCR.

## Requirements (đã chốt với chủ dự án)
- Lọc: bất kỳ bài nào liên quan ≥1 mã CK VN (option "a").
- Lưu: tiêu đề, **toàn văn body**, thời gian đăng, **danh sách mã CK liên quan**.
- Cửa sổ thời gian: tham số `hours`, mặc định 1h (giống HNX/HSX).
- Storage: **bảng mới** `cafef_articles` (S1), không đụng `trading_changes`.

## Approaches đã cân nhắc

### Storage
- **S1 bảng mới `cafef_articles` — CHỌN.** 1 bài = 1 dòng, body không lặp, mã gom mảng.
- S2 ép vào `trading_changes` — LOẠI. Không có cột body; model "1 dòng/mã" làm body
  nhân bản (vi phạm DRY); trộn 2 thực thể khác bản chất; `pdf_url` lệch nghĩa.

### Flow
- **Flow A fetch-then-extract — CHỌN.** Lấy list → tải từng bài → bóc mã → có mã thì lưu.
  Đơn giản, ít sót; hợp cửa sổ 1h (ít bài).
- Flow B classify-first (LLM lọc title theo lô) — LOẠI. Title CafeF hay giấu mã
  ("một doanh nghiệp...") → lọc theo title dễ sót, lợi ích thấp với filter rộng.

### Trích xuất mã CK
- **E1 parser thuần (regex link CafeF) — CHỌN.** Bóc mã + sàn từ link
  `du-lieu/(hose|hnx|upcom)/<code>`, khối "TIN TỨC SỰ KIỆN VỀ", thẻ "Từ Khóa".
  Miễn phí, xác định, nhanh. Nhược: sót mã chỉ có trong prose không link.
- E2 LLM bóc từ body — LOẠI (bản đầu). Tốn token.
- E3 hybrid — để dành nâng cấp nếu E1 sót nhiều.

## Recommended solution (final)

Module CafeF riêng, **không dùng lại `run_pipeline`** (pipeline cũ gắn chặt PDF).

```
POST /crawl/cafef?hours=1
  fetch_cafef_list(hours)        -> [{article_id, url, title, published_at?}]  (phân trang, dừng khi cũ hơn cửa sổ)
  for each article:
    fetch_cafef_article(url)     -> html
    parse_cafef_article(html)    -> {title, body, published_at, stock_codes}   (E1)
    lọc chính xác theo published_at trong trang bài
    stock_codes rỗng -> bỏ
  insert_cafef_articles(records) -> 1 bài = 1 dòng
  -> stats (style HNX/HSX)
```

### Schema
```sql
CREATE TABLE IF NOT EXISTS cafef_articles (
    id                BIGSERIAL PRIMARY KEY,
    source_article_id VARCHAR(64) NOT NULL,
    url               TEXT NOT NULL,
    title             TEXT NOT NULL,
    body              TEXT,
    published_at      TIMESTAMPTZ,
    stock_codes       TEXT[],
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### Module mới (theo pattern deep-module hiện có)
- `app/fetchers/cafef.py` — IO: tải list + tải bài (requests, User-Agent).
- `app/parsers/cafef_list.py` — pure: HTML list -> `[{article_id, url, title, published_at?}]`.
- `app/parsers/cafef_article.py` — pure: HTML bài -> `{title, body, published_at, stock_codes}` (E1).
- `app/pipeline_cafef.py` — điều phối Flow A.
- `app/db.py` — thêm `_CREATE_CAFEF_SQL` + `insert_cafef_articles()`; `init_db()` tạo cả 2 bảng.
- `app/routes.py` — thêm `POST /crawl/cafef`.
- `requirements.txt` — thêm `beautifulsoup4`.

### Chi tiết parser đã xác minh trên trang thật
- Tiêu đề: `<h1>`.
- Thời gian: byline `%d-%m-%Y - %I:%M %p`, giờ VN (GMT+7).
- Body: khối nội dung chi tiết (các `<p>`).
- Mã CK: link `cafef.vn/du-lieu/(hose|hnx|upcom)/<code>-...`, khối "TIN TỨC SỰ KIỆN VỀ:
  .../(hose|hnx|upcom)/<CODE>-...", thẻ "Từ Khóa" `cafef.vn/<code>.html`.

## Risks & mitigations
- **Endpoint phân trang mục CK** chưa xác nhận → dò DevTools khi implement; fallback đọc
  trực tiếp trang mục (≈trang 1). Cửa sổ 1h thường nằm gọn trang đầu.
- **Thời gian tương đối trên list** ("8 giờ trước") → dùng để dừng phân trang thô,
  lọc chính xác bằng `published_at` bóc từ trang bài.
- **Resilient**: 1 bài lỗi -> skip + đếm `errors_count`, không chết cả mẻ.
- **Anti-bot/JS**: hiện trang server-render đủ, requests là đủ; Playwright chỉ là dự phòng.
- **Không dedup** (đúng triết lý dự án — cửa sổ giờ tự giới hạn).

## Success metrics / validation
- `POST /crawl/cafef?hours=1` trả stats: số bài tìm, số bài có mã (đã lưu), số lỗi.
- Kiểm 1 bài mẫu (vd PNJ): row có body đầy đủ, `stock_codes` chứa PNJ, `published_at` đúng.
- Bài không mã VN (vàng/bạc/quốc tế) không bị lưu.

## Next steps / dependencies
- Xác nhận endpoint phân trang CafeF (DevTools).
- Thêm `beautifulsoup4`.
- Triển khai theo thứ tự: parser bài -> parser list -> fetcher -> db -> pipeline -> route.
