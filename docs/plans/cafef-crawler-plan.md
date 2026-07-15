---
title: "Implementation Plan — Python CafeF crawler"
status: ready
created: 2026-07-14
updated: 2026-07-15
source_brainstorm: docs/brainstorm/cafef-crawler-2026-07-14.md
blockedBy: []
blocks: []
---

# Implementation Plan — Python CafeF crawler

## Tổng quan

Thêm nguồn CafeF (`https://cafef.vn/thi-truong-chung-khoan.chn`) vào NewsCrawler bằng Python. Mỗi lần chạy lấy **toàn bộ bài trong cửa sổ `hours` gần nhất**, mặc định 1 giờ giống HNX/HSX; không giới hạn số bài. Module bóc `title`, `published_at`, toàn văn `body`, nhận diện best-effort mã chứng khoán Việt Nam từ metadata/link có cấu trúc và lưu bài hợp lệ vào bảng riêng `cafef_articles`.

Giữ kiến trúc hiện tại: function-based, `requests` cho IO, BeautifulSoup/lxml cho parser, psycopg3 cho PostgreSQL, FastAPI cho route, logging chuẩn project và timezone `Asia/Ho_Chi_Minh`.

## Phạm vi và quyết định

- API: `POST /crawl/cafef?hours=1`; dùng `DEFAULT_CRAWL_HOURS` như HNX/HSX.
- Phân trang category cho đến khi gặp bài cũ hơn cutoff; không có `limit` theo số bài.
- Điều kiện dừng an toàn: hết trang, trang không có ID mới, hoặc đã đi qua ranh giới cutoff trên danh sách có thứ tự giảm dần.
- Dùng HTTP server-rendered + BeautifulSoup; chưa thêm Playwright Python.
- Flow riêng: list pages → article detail → parse → lọc thời gian/mã CK → lưu DB.
- Không tái sử dụng `run_pipeline()` vì pipeline hiện tại gắn với PDF, OCR và LLM.
- Không sửa schema/behavior HNX, HSX và bảng `trading_changes`.
- Không dùng Anthropic cho CafeF; không thêm library mới.
- Không thêm automated test suite trong iteration này; validation bằng smoke check parser, API và DB thật.

### Contract nhận diện mã CK

E1 parser thuần chỉ dùng hai tín hiệu có cấu trúc, độ chính xác cao:

1. `href` khớp `(?:https?://cafef\.vn)?/du-lieu/(?:hose|hnx|upcom)/([a-z0-9]{3})-`.
2. Widget `.chisochungkhoan iframe[src*="symbol="]`: parse query parameter `symbol`, chỉ nhận `^[A-Z0-9]{3}$`; fallback `.chisochungkhoan h2.title_box` khớp `^([A-Z0-9]{3}):`.

Chuẩn hóa uppercase, unique, giữ thứ tự. Không dùng regex token viết hoa trong prose hoặc tag `/xxx.html` vì thiếu ticker master. E1 là best-effort và có thể bỏ sót mã chỉ xuất hiện trong prose. Recall tuyệt đối cần plan riêng cho ticker master hoặc LLM hybrid.

## Kết quả khảo sát codebase

- Entry point: `main.py`; route tại `app/routes.py`; startup gọi `init_db()`.
- Pattern: `fetchers/` phụ trách IO, `parsers/` thuần, pipeline điều phối, `db.py` lưu dữ liệu.
- `app/pipeline.py` import `httpx` không dùng trong khi requirements không có; cần xóa ở preflight.
- Config bắt buộc `DATABASE_URL` và `ANTHROPIC_API_KEY` khi import; giữ nguyên trong scope này.
- Chỉ có một plan CafeF đang hoạt động (file này), không có cross-plan dependency.

## DOM CafeF đã xác nhận

| Dữ liệu | Selector chính | Fallback/ghi chú |
|---|---|---|
| List item | `.box-category-item` | một item/bài |
| Link/title list | `.box-category-item h3 a` | URL canonical CafeF |
| Thời gian list | `.box-category-item .time[title]` | `title` ISO; chỉ là hint để dừng trang |
| Article ID | URL `-(\d+)\.chn$` | bỏ item không ID |
| Tiêu đề detail | `h1[data-role="title"]` | fallback `h1.title`, rồi `<h1>` |
| Ngày detail | `[data-role="publishdate"]` | `datetime` là nguồn authoritative |
| Sapo | `[data-role="sapo"]` | có thể vắng |
| Content root | `[data-role="content"]` | class hiện tại `detail-content afcbc-body` |

### Contract body-cleaning

1. Parse riêng content root rồi `decompose()` các selector: `script`, `style`, `iframe`, `figure`, `figcaption`, `.VCSortableInPreviewMode`, `.PhotoCMS_Caption`, `.tindnd`, `#listNewsInContent`, `[data-marked-zoneid]`, `.chisochungkhoan`, `.h-show-pc`, `.h-show-mobile`, `[class*="banner"]`, `[id^="admzone"]`.
2. Lấy candidates `p, h2, h3, blockquote, li` còn lại theo thứ tự DOM.
3. Chỉ giữ leaf semantic candidate: node không chứa descendant cũng khớp candidate selector; tránh lặp text node cha/con.
4. Normalize whitespace, bỏ rỗng, dedup text giống hệt; prepend sapo nếu khác đoạn đầu.
5. Caption/figure/ad/related/widget không thuộc body; heading/list/blockquote hợp lệ thuộc body.

Smoke oracle: body bắt đầu bằng sapo nếu có, chứa leaf candidate đầu/cuối, số đoạn khớp số candidate hợp lệ và không chứa text của noise subtree.

## Data contract

### List item

```python
{
    "article_id": str,
    "url": str,
    "list_title": str,
    "published_at_hint": datetime | None,
}
```

### Parsed article

```python
{
    "source_article_id": str,
    "url": str,
    "title": str,
    "published_at": datetime | None,
    "body": str,
    "stock_codes": list[str],
}
```

Record chỉ persist khi date timezone-aware, body không rỗng và codes có ít nhất một phần tử.

### Pipeline stats và invariants

```python
{
    "source": "cafef",
    "window_hours": float,
    "pages_fetched": int,
    "articles_found": int,       # article ID unique thấy trước khi dừng
    "articles_parsed": int,      # đủ title + body
    "articles_in_window": int,   # cutoff <= detail date <= start + 5 phút
    "articles_with_codes": int,  # in-window + E1 tìm thấy mã
    "records_inserted": int,
    "errors_count": int,
}
```

Invariant: `articles_found >= articles_parsed >= articles_in_window >= articles_with_codes >= records_inserted`. Sau insert, cộng `len(records_attempted) - records_inserted` vào errors để phản ánh lỗi DB per-row.

## Database

```sql
CREATE TABLE IF NOT EXISTS cafef_articles (
    id                BIGSERIAL PRIMARY KEY,
    source_article_id VARCHAR(64) NOT NULL,
    url               TEXT NOT NULL,
    title             TEXT NOT NULL,
    body              TEXT NOT NULL,
    published_at      TIMESTAMPTZ NOT NULL,
    stock_codes       TEXT[] NOT NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (cardinality(stock_codes) > 0)
);
```

Không thêm unique constraint/dedup theo quyết định hiện tại: cùng bài có thể được insert lại ở lần gọi sau. Stats được tính theo từng lần chạy.

## File thay đổi

| File | Thay đổi |
|---|---|
| `app/parsers/cafef_list.py` | Parse từng page, ID/URL/title/date hint |
| `app/parsers/cafef_article.py` | Title/date/body-cleaning/E1 stock codes |
| `app/fetchers/cafef.py` | Category pagination + article GET dùng shared session |
| `app/pipeline_cafef.py` | Điều phối theo time window và stats |
| `app/db.py` | Tạo `cafef_articles`, insert function |
| `app/routes.py` | Thêm `POST /crawl/cafef?hours=` |
| `app/pipeline.py` | Xóa import `httpx` không dùng; không sửa logic |
| `main.py` | Cập nhật description/log để nêu CafeF/bảng mới |
| `.env.example`, `app/config.py`, `requirements.txt` | Không đổi |

## Kế hoạch triển khai

### Phase 0 — Recon pagination và HTTP

- [ ] Xóa import `httpx` không dùng trong `app/pipeline.py`.
- [ ] Dùng Python `requests` GET category và article mẫu; xác nhận status 200, UTF-8, DOM server-rendered.
- [ ] Dò endpoint load-more/timeline của CafeF; ghi URL, method, params, response format và cách tăng page.
- [ ] Xác nhận page 1 và page 2 không trùng toàn bộ; article ID unique; thứ tự publish giảm dần qua ranh giới hai page.
- [ ] Xác nhận `.time[title]` là ISO-aware trên list; detail `[data-role=publishdate][datetime]` là nguồn lọc chính xác.
- [ ] Xác nhận body/noise rules và E1 positive/negative samples.
- [ ] Nếu không tìm được endpoint pagination, dừng để re-plan; không chấp nhận fallback chỉ page 1 vì có thể bỏ sót bài trong 1 giờ khi tin nhiều.
- [ ] Nếu requests bị chặn/thiếu DOM, dừng để re-plan Playwright Python.

**Acceptance:** biết cách tải page N đến khi qua cutoff; requests đọc đúng list/detail; thứ tự list được chứng minh.

### Phase 1 — Pure parsers

- [ ] Tạo `parse_cafef_list(html: str) -> list[dict]` cho page/fragment bất kỳ.
- [ ] Dedup nội bộ theo article ID, giữ thứ tự DOM, chỉ nhận CafeF HTTPS article URL.
- [ ] Parse `published_at_hint` từ `.time[title]`, timezone-aware VN; malformed hint trả None.
- [ ] Tạo `parse_cafef_article(html: str, article_id: str, url: str) -> dict | None`.
- [ ] Parse detail ISO datetime trước; fallback visible formats thực tế; gắn VN timezone.
- [ ] Thực hiện body-cleaning đúng contract leaf candidates.
- [ ] Thực hiện E1 đúng hai structured signals; không scan prose/tag chung.
- [ ] Thiếu title/body là parse failure; thiếu date để pipeline reject; thiếu mã trả list rỗng.

**Acceptance:** list parser chạy trên ít nhất hai pages; detail parser đạt body oracle; PNJ nhận diện đúng; negative sample codes rỗng.

### Phase 2 — CafeF fetcher và pagination

- [ ] Tạo category/base/timeline URL và browser-like headers trong `app/fetchers/cafef.py`.
- [ ] `fetch_cafef_list_page(session, page) -> str | None` dùng endpoint đã xác nhận và timeout `(5, HTTP_TIMEOUT)`.
- [ ] `fetch_cafef_article(session, url) -> str | None` dùng cùng session.
- [ ] Fetcher không sở hữu session; pipeline mở/đóng một shared session cho cả batch.
- [ ] Log page number, HTTP status và lỗi; lỗi một article không chết batch.

**Acceptance:** fetch được liên tiếp nhiều pages và detail bằng một session; page hết dữ liệu trả empty/None rõ ràng.

### Phase 3 — Persistence

- [ ] Thêm `_CREATE_CAFEF_SQL`; `init_db()` tạo cả hai bảng và log rõ tên.
- [ ] Tạo `insert_cafef_articles(records: list[dict]) -> int` resilient per-row.
- [ ] Để psycopg map `list[str]` sang `TEXT[]`; log article ID khi insert lỗi.
- [ ] Không thay đổi schema/function HNX-HSX.

**Acceptance:** insert hợp lệ giữ Unicode/timezone/codes; DB reject date null/codes rỗng; trading_changes không đổi.

### Phase 4 — Dedicated CafeF pipeline theo time window

- [ ] Tạo `run_cafef_pipeline(window_hours: float) -> dict`.
- [ ] Capture `run_started_at` VN; `cutoff = start - hours`; upper bound = start + 5 phút clock-skew tolerance.
- [ ] Mở shared session, bắt đầu page 1 và duy trì global `seen_article_ids`.
- [ ] Với mỗi list item chưa thấy: dùng hint để nhận biết boundary, tải detail, parse và dùng detail date làm authoritative.
- [ ] Chỉ persist khi `cutoff <= published_at <= upper_bound` và E1 có codes.
- [ ] Khi gặp detail cũ hơn cutoff trong list đã xác nhận giảm dần, dừng phần còn lại và không tải page tiếp.
- [ ] Nếu hint/date thiếu hoặc một item lỗi, không dùng item đó làm boundary; tiếp tục để tránh bỏ sót.
- [ ] Nếu cả page không có ID mới hoặc endpoint trả empty, dừng để tránh vòng lặp vô hạn.
- [ ] Nếu page hiện tại còn toàn bài trong window, tăng page và tiếp tục; không đặt article-count cap.
- [ ] Cập nhật counters/invariants; ngoài window và không codes không phải error; malformed date/fetch/DB failure là error.
- [ ] Không log body ở INFO.

**Acceptance:** pipeline tự dừng theo cutoff/hết trang, không theo số bài; nếu hơn 20 bài trong 1 giờ vẫn đi page tiếp và xử lý đủ.

### Phase 5 — FastAPI wiring

- [ ] Thêm `POST /crawl/cafef` với `hours > 0`, default `DEFAULT_CRAWL_HOURS` bằng `Query`, giống HNX/HSX.
- [ ] Gọi `run_cafef_pipeline(hours)` và trả `_serialize_stats(stats)`.
- [ ] Cập nhật routes docstring và FastAPI description trong `main.py`.
- [ ] Không đổi contract `/crawl/hnx`, `/crawl/hsx`, `/health`.

**Acceptance:** `/crawl/cafef` mặc định 1 giờ; custom hours hoạt động; hours không hợp lệ trả 422.

### Phase 6 — Validation end-to-end

- [ ] Chạy compile/import check với env hợp lệ.
- [ ] Smoke parser trên HTML list nhiều pages và các detail đại diện.
- [ ] Gọi `POST /crawl/cafef` không truyền params; xác nhận `window_hours=1`.
- [ ] Gọi `POST /crawl/cafef?hours=24` để buộc pagination; xác nhận `pages_fetched > 1` khi dữ liệu đủ.
- [ ] Kiểm mọi detail date trong DB thuộc window/tolerance, body sạch, codes không rỗng.
- [ ] Mô phỏng page trùng/empty và một article lỗi để xác nhận dừng an toàn, batch tiếp tục và stats đúng.
- [ ] Smoke-check `/health`, `/crawl/hnx`, `/crawl/hsx` không regression.

**Acceptance:** crawler lấy đủ bài theo hours qua nhiều page, dừng đúng cutoff và không giới hạn số article.

## Rủi ro và cách xử lý

| Rủi ro | Xử lý |
|---|---|
| Endpoint pagination đổi | Cô lập URL/params trong fetcher; recon trước implement |
| List không thật sự sorted | Phase 0 xác minh; detail date authoritative; không dùng item lỗi làm boundary |
| Relative/missing list time | Chỉ dùng hint tối ưu; detail datetime quyết định lọc |
| CafeF đổi class | Ưu tiên `data-role`, fallback có thứ tự, selector tập trung trong parser |
| Requests bị anti-bot | Stop gate Phase 0; chỉ đề xuất Playwright khi có bằng chứng |
| Caption/related lọt body | Noise selector đóng + leaf candidates + smoke oracle |
| E1 bỏ sót mã prose | Contract best-effort; ticker master/LLM là iteration riêng |
| Nhiều bài trong một giờ làm request lâu | Không cap để bảo toàn completeness; shared session + per-request timeout |
| Insert trùng cross-run | Chấp nhận có chủ đích trong v1; stats theo lần chạy |

## Out of scope

- Scheduler/cron, auth, proxy/captcha bypass.
- Playwright Python, async/concurrency, retry library mới, total batch deadline.
- Ticker master, LLM/hybrid extraction và guarantee mọi mã trong prose.
- Dedup/idempotency và migration framework.
- Các chuyên mục CafeF khác.
- Automated test suite trong iteration này.

## Tiêu chí hoàn thành

1. `POST /crawl/cafef` mặc định crawl toàn bộ bài 1 giờ gần nhất.
2. `POST /crawl/cafef?hours=N` crawl đúng cửa sổ N giờ qua đủ pages cần thiết.
3. Không có article-count limit; dừng bằng cutoff, empty page hoặc no-new-ID guard.
4. Mỗi row có ID, canonical URL, title, date aware hợp lệ, body sạch và ít nhất một E1 code.
5. Chỉ lưu bài trong `[cutoff, run_started_at + 5 phút]` và có structured code signal.
6. Lỗi một bài không làm hỏng partial result; stats giữ invariants.
7. HNX/HSX và `trading_changes` không thay đổi hành vi.

## Handoff

Triển khai Phase 0 → 6. Pagination recon là stop gate đầu tiên; không chấp nhận implementation chỉ đọc page đầu vì sẽ vi phạm yêu cầu lấy toàn bộ bài trong time window.
