---
title: "Implementation Plan — CafeF crawler"
status: pending
created: 2026-07-14
source_brainstorm: docs/brainstorm/cafef-crawler-2026-07-14.md
related_prd: docs/prd/news-crawler-hnx-hsx.md
---

# Implementation Plan — CafeF crawler

Mục tiêu: thêm nguồn CafeF, crawl toàn văn bài viết liên quan ≥1 mã CK VN,
lưu vào bảng mới `cafef_articles`. Storage S1, Flow A, trích mã E1 (parser thuần).

Thứ tự triển khai: **parser bài → parser list → fetcher → db → pipeline → route**
(bottom-up: đơn vị thuần trước, IO/điều phối sau).

---

## Phase 0 — Chuẩn bị & recon
- [ ] 0.1 Thêm `beautifulsoup4` vào `requirements.txt`, cài vào `.venv`.
- [ ] 0.2 Dò DevTools endpoint phân trang mục chứng khoán CafeF:
  - Cuộn/tải thêm ở `thi-truong-chung-khoan.chn`, bắt request timeline (nghi
    `/timeline/{cateId}/trang-{n}.chn` hoặc tương tự).
  - Ghi lại: URL, params, format response (HTML fragment / JSON), cách suy ra
    `article_id`, `title`, `url`, thời gian.
  - Fallback nếu không tìm ra: chỉ đọc trang mục (≈trang 1) — đủ cho cửa sổ 1h.
- [ ] 0.3 Lưu 1–2 file HTML mẫu (1 trang list + 1 trang bài PNJ) làm fixture tham chiếu.

**Acceptance:** biết chắc cách lấy danh sách bài nhiều trang (hoặc xác nhận dùng fallback).

---

## Phase 1 — `parsers/cafef_article.py` (pure, E1)
Input: HTML 1 bài. Output: `{title, body, published_at, stock_codes}`.
- [ ] 1.1 Bóc `title` từ `<h1>`.
- [ ] 1.2 Bóc `published_at`: parse byline `%d-%m-%Y - %I:%M %p`, gắn tz Asia/Ho_Chi_Minh.
  - Xử lý fallback nếu byline khác format → trả `None`, log warning.
- [ ] 1.3 Bóc `body`: gom text các `<p>` trong khối nội dung chi tiết
  (xác định selector khối content khi xem HTML thật; loại bỏ box "Đọc thêm",
  "TIN TỨC SỰ KIỆN", ads, related).
- [ ] 1.4 Bóc `stock_codes` (E1):
  - Regex trên href: `cafef\.vn/du-lieu/(hose|hnx|upcom)/([a-z0-9]+)-`
  - Khối "TIN TỨC SỰ KIỆN VỀ": `/(hose|hnx|upcom)/([A-Z0-9]+)-`
  - Thẻ "Từ Khóa": `cafef\.vn/([a-z0-9]+)\.html` (lọc chỉ giữ token giống mã: 3 ký tự A–Z, tùy chọn)
  - Chuẩn hóa: upper-case, unique, giữ thứ tự xuất hiện.
- [ ] 1.5 Test tay bằng HTML fixture PNJ: kỳ vọng `stock_codes` chứa `PNJ`,
  body đầy đủ, `published_at` = 2026-07-13 12:30 (+07).

**Acceptance:** hàm chạy trên fixture cho ra dict đúng 4 field; bài không mã → `stock_codes == []`.

---

## Phase 2 — `parsers/cafef_list.py` (pure)
Input: HTML/fragment trang list. Output: `[{article_id, url, title, published_at?}]`.
- [ ] 2.1 Bóc các link bài trong mục CK (loại link sidebar "MỚI NHẤT", menu, ad).
- [ ] 2.2 Suy `article_id` từ đuôi URL `-(\d+)\.chn`.
- [ ] 2.3 Lấy `title` từ text link; `published_at` thô nếu có (có thể `None`).
- [ ] 2.4 Test tay bằng fixture list.

**Acceptance:** trả danh sách bài đúng, `article_id` số, không lẫn link rác.

---

## Phase 3 — `fetchers/cafef.py` (IO)
- [ ] 3.1 `fetch_cafef_list(window_hours) -> list[dict]`:
  - Phân trang tăng dần (theo endpoint Phase 0), gọi `parse_cafef_list`.
  - Dừng khi gặp bài rõ ràng cũ hơn cutoff (dựa thời gian thô list) hoặc hết trang.
  - `time.sleep(0.3)` giữa trang; header User-Agent như hnx/hsx.
- [ ] 3.2 `fetch_cafef_article(url) -> str | None`: GET HTML, raise_for_status, trả text.
- [ ] 3.3 Logging + try/except theo phong cách hnx.py/hsx.py (resilient, trả None khi lỗi).

**Acceptance:** gọi thật `fetch_cafef_list(1)` trả vài bài; `fetch_cafef_article` trả HTML bài.

---

## Phase 4 — `db.py` (bảng + insert)
- [ ] 4.1 Thêm `_CREATE_CAFEF_SQL` (schema `cafef_articles` theo brainstorm).
- [ ] 4.2 `init_db()` tạo cả `trading_changes` + `cafef_articles`.
- [ ] 4.3 `insert_cafef_articles(records) -> int`:
  - Insert từng dòng; `stock_codes` map sang `text[]` (psycopg list adaptation).
  - Resilient per-row như `insert_records`; trả số dòng insert.

**Acceptance:** chạy `init_db()` tạo bảng; insert 1 record mẫu ok, `stock_codes` lưu dạng mảng.

---

## Phase 5 — `pipeline_cafef.py` (điều phối Flow A)
- [ ] 5.1 `run_cafef_pipeline(window_hours) -> dict`:
  - Bước 1: `fetch_cafef_list(hours)`.
  - Bước 2: mỗi bài → `fetch_cafef_article` → `parse_cafef_article`.
  - Bước 3: lọc chính xác `published_at >= cutoff` (giờ VN); bỏ nếu `stock_codes` rỗng.
  - Bước 4: build record → `insert_cafef_articles`.
  - Stats: `articles_found`, `articles_with_codes`, `records_inserted`, `errors_count`, timing.
- [ ] 5.2 Resilient: 1 bài lỗi → skip + `errors_count += 1`, không dừng mẻ.
- [ ] 5.3 Logging theo style `pipeline.py` (step markers, timing).

**Acceptance:** chạy pipeline với hours nhỏ, trả stats hợp lý; DB có bài kèm mã.

---

## Phase 6 — `routes.py` (API)
- [ ] 6.1 `POST /crawl/cafef?hours=` (default `DEFAULT_CRAWL_HOURS`), gọi `run_cafef_pipeline`.
- [ ] 6.2 Trả `_serialize_stats(stats)`.

**Acceptance:** `POST /crawl/cafef?hours=1` trả JSON stats; `GET /health` vẫn ok.

---

## Phase 7 — Validation end-to-end
- [ ] 7.1 Chạy app (PyCharm `__main__`), gọi `POST /crawl/cafef?hours=3`.
- [ ] 7.2 Kiểm DB:
  - Bài PNJ: có `body`, `stock_codes` chứa `PNJ`, `published_at` đúng, `url`/`source_article_id` đúng.
  - Bài vàng/bạc/quốc tế không mã VN → không có trong bảng.
- [ ] 7.3 Kiểm resilient: chỉnh 1 URL hỏng → mẻ vẫn chạy, `errors_count` tăng.

**Acceptance:** dữ liệu đúng kỳ vọng, không crash, stats khớp thực tế.

---

## Out of scope (giữ như PRD gốc)
- Dedup/idempotency, LLM (E2/E3), Playwright, cron/scheduler, auth, test tự động.
- Các mục CafeF khác ngoài `thi-truong-chung-khoan`.

## Notes cho người triển khai
- Tôn trọng phong cách dự án: **function-based**, config từ `.env`, resilient per-item,
  logging theo `LOG_LEVEL`, giờ VN `Asia/Ho_Chi_Minh`.
- Không sửa `run_pipeline`, `trading_changes`, luồng HNX/HSX.
- Nếu E1 sót mã nhiều khi test thực tế → mở issue nâng E3 (thêm LLM fallback).
