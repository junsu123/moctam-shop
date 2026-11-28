# Tài liệu API

Mọi phản hồi là JSON UTF-8. Tiền tính bằng số nguyên VND. Mốc thời gian theo UTC, định dạng `YYYY-MM-DD HH:MM:SS`.

## Mã lỗi ổn định

Lỗi trả về theo dạng `{"error": {"code": "...", "message": "...", "details": {...}}}`.

| HTTP | code | Khi nào | details |
|---|---|---|---|
| 422 | VALIDATION_ERROR | Dữ liệu không hợp lệ | `fields: {tên_trường: thông báo}`, để hiện lỗi ngay cạnh ô nhập |
| 409 | QUOTE_CHANGED | Giá, ưu đãi hoặc phí đổi, hoặc báo giá hết hạn; voucher vừa hết lượt | `quote`: báo giá mới để khách xác nhận |
| 409 | OUT_OF_STOCK | Hết hàng hoặc không đủ số lượng | `issues[]`, `quote` |
| 422 | ZONE_NOT_SERVED | Tỉnh/thành chưa được phục vụ | `quote` |
| 409 | IDEMPOTENCY_CONFLICT | Cùng `Idempotency-Key` nhưng khác nội dung hoặc khác phiên | — |
| 400 | IDEMPOTENCY_KEY_REQUIRED | Thiếu khóa gửi lại, hoặc khóa sai định dạng (16–80 ký tự `[A-Za-z0-9_-]`) | — |
| 419 | CSRF_INVALID | Thiếu hoặc sai `X-CSRF-Token` | — |
| 429 | RATE_LIMITED | Gửi quá nhiều yêu cầu | — |
| 401/403 | UNAUTHENTICATED / FORBIDDEN | Khóa API sai hoặc thiếu quyền | — |
| 410 | CURSOR_EXPIRED | Con trỏ đồng bộ cũ hơn mốc đã dọn | `pruned_through` |
| 409 | SOURCE_OUTDATED | Bản nháp AI dựa trên thông tin nhãn cũ (trả trong `results[]`) | — |
| 423 | AI_PUBLISH_DISABLED | `POST /api/sync/publish` khi website tắt AI tự xuất bản (cài đặt `ai_publish_enabled`) | — |
| 409 | AI_PUBLISH_HOURS | Xuất bản ngoài khung giờ `ai_publish_hours` (mặc định 07:00–21:30 giờ Việt Nam) | — |
| 429 | AI_PUBLISH_QUOTA | Hết hạn mức AI xuất bản trong ngày theo loại (`ai_publish_limit_faq` = 3, `ai_publish_limit_blog` = 1) | `used`, `limit` |

Trong voucher của báo giá: `VOUCHER_INVALID`, `VOUCHER_EXPIRED`, `VOUCHER_EXHAUSTED`, `VOUCHER_NOT_APPLICABLE`, `VOUCHER_MIN_NOT_MET`.

## API công khai

### POST /api/quote

```json
{"items": [{"sku_id": 1, "qty": 2}], "voucher_code": "CHAOBAN20", "province": "Hà Nội"}
```

Phản hồi `200`:

```json
{"quote": {
  "lines": [{"sku_id": 1, "sku_code": "TRA-GUNG-20", "product_name": "Trà gừng mật ong", "variant_label": "Hộp 20 túi x 2g",
             "list_price": 65000, "unit_price": 52000, "flash_sale_id": 1, "voucher_eligible": false, "qty": 2, "line_total": 104000, "available": 118}],
  "issues": [],
  "goods_subtotal": 104000,
  "voucher": {"code": "CHAOBAN20", "valid": false, "discount": 0, "error_code": "VOUCHER_NOT_APPLICABLE", "message": "..."},
  "discount": 0,
  "shipping": {"served": true, "zone_id": 1, "zone_name": "Hà Nội", "rate_id": 1, "fee": 20000, "eta": "1–2 ngày", "free_from": 400000},
  "total": 124000,
  "expires_at": "2026-11-25 06:15:00",
  "fingerprint": "…", "quote_token": "…"
}}
```

### POST /api/orders

Header bắt buộc: `Idempotency-Key: <16–80 ký tự>` và `X-CSRF-Token: <thẻ meta csrf-token>`. Cookie phiên phải đi kèm.

```json
{"items": [{"sku_id": 1, "qty": 2}], "voucher_code": "", "payment_method": "vietqr",
 "quote_token": "<từ /api/quote>", "marketing_consent": true,
 "customer": {"name": "Trần Thị Mai", "phone": "0987654321", "province": "Hà Nội", "address": "25 Ngõ Huế", "note": ""}}
```

- `201` (đơn mới) hoặc `200` (gửi lại, `"replayed": true`) trả `{"order": {code, status, total, expires_at, items, vietqr: {bank_name, account_no, account_name, amount, content, qr_payload}, confirm_url}}`.
- `409 QUOTE_CHANGED`: hiện `details.quote` cho khách. Khi khách đồng ý, gửi lại với `details.quote.quote_token`; có thể giữ nguyên `Idempotency-Key`.

### POST /api/chat

Gửi `{"message": "Matcha còn hàng không?"}`. Phản hồi có dạng `{"reply": "...", "source": "live|label|faq|fallback", "products": [...], "suggestions": [...], "faq": {...}, "support": {...}}`.

### GET /api/products?q=&category=&page=&per_page=

Tìm sản phẩm công khai, có phân trang. Dùng cho ô gợi ý tìm kiếm.

### GET /api/health

Trả `{"ok": true, "time": "..."}`, dùng cho dịch vụ giám sát ngoài.

## API đồng bộ (cho dịch vụ Python)

Header: `Authorization: Bearer <khóa>`. Tạo khóa ở Quản trị → Khóa API Python, hoặc chạy `php bin/create_api_key.php`.

### GET /api/sync/events?after=&lt;seq&gt;&limit=500  — quyền `events:read`

```json
{"events": [{"seq": 259, "event_id": "01JD…", "entity_type": "order", "entity_id": 54, "event_type": "order.status_changed",
             "payload": {"order_id": 54, "code": "TM261125ZRV9", "status": "confirmed", "payment_method": "vietqr", "payment_status": "paid",
                         "customer_key": "a1b2…", "marketing_consent": true, "zone_id": 3, "goods_subtotal": 341000, "voucher_code": "CHAOBAN20",
                         "total": 356000, "created_at": "…", "delivered_at": null,
                         "items": [{"sku_id": 1, "product_id": 1, "category_id": 1, "qty": 1, "unit_price": 52000}], "version": 259}}],
 "next_cursor": 259, "has_more": false}
```

Loại sự kiện: `order.created`, `order.status_changed`, `order.payment_changed`, `order.flagged`, `product.updated` (payload `{product_id, category_id, status, info_version}`).

### GET /api/sync/snapshot?after_id=0&limit=500  — quyền `events:read`

Trả `{"as_of_seq": 258, "orders": [...], "products": [...], "next_after_id": 54}`. Đọc `as_of_seq` từ trang đầu tiên; sau khi tải đủ các trang, đặt con trỏ bằng giá trị đó.

### GET /api/sync/catalog  — quyền `catalog:read`

Trả `categories` (kèm `repurchase_days`), `products` (thông tin nhãn đã duyệt, `info_version`, `skus`), `published_faqs` (kèm `search_text`, `version_id`), `published_blogs` (`id, product_id, category_id, title`: để AI không soạn trùng bài nhân viên đã viết) và `unanswered_questions` (30 ngày gần nhất, đã che SĐT/email).

### GET /api/sync/feedback?since=YYYY-MM-DD[%20HH:MM:SS]  — quyền `catalog:read`

Kết quả duyệt các bản nháp AI đã nhận (mặc định 120 ngày gần nhất), dùng cho bộ não Python học từ phản hồi của nhân viên. API không trả dữ liệu khách hàng.

```json
{"items": [
  {"client_ref": "faq:q:3f2a…", "kind": "faq", "received_at": "…", "status": "rejected", "note": "Sai giọng văn, không hứa giao trong ngày", "reviewed_at": "…"},
  {"client_ref": "blog:product:5v3", "kind": "blog", "status": "edited", "note": "Rút gọn mở bài", "reviewed_at": "…"},
  {"client_ref": "xs:1:3:2026w48", "kind": "cross_sell", "status": "approved"},
  {"client_ref": "care-20261125", "kind": "care_list", "status": "pending", "counts": {"pending": 12, "contacted": 5, "skipped": 1}}
 ],
 "backlog": {"faq": 2, "blog": 1, "cross_sell": 4, "care": 12, "oldest_pending_at": "2026-11-20 03:10:00"},
 "generated_at": "…"}
```

`status`: `pending` · `approved` (duyệt nguyên văn) · `edited` (sửa rồi mới xuất bản) · `rejected` (kèm `note`) · `retracted` (đã gỡ) · `invalid` (website từ chối khi nhận, ví dụ `SOURCE_OUTDATED`) · `duplicate` (cặp mua kèm đã có) · `gone` (đã xóa) · `done` (danh sách chăm sóc đã xử lý hết). `client_ref` là mã đã lọc ký tự, chỉ giữ `[A-Za-z0-9_.:-]`.

### POST /api/sync/drafts  — quyền `drafts:write`

```json
{"items": [
  {"client_ref": "faq:q:3f2a…", "kind": "faq",  "data": {"title": "...", "body": "...", "body_is_text": true, "keywords": "...", "product_id": 5,
                                                          "source_refs": [{"product_id": 5, "info_version": 3}], "generated_by": "claude-haiku-5-5"}},
  {"client_ref": "blog:product:5@v3", "kind": "blog", "data": {"title": "...", "meta_description": "...", "body": "<p>…</p>", "source_refs": [...]}},
  {"client_ref": "xs:1:3:2026w48", "kind": "cross_sell", "data": {"product_id": 1, "related_product_id": 3, "score": 0.8, "reason": "..."}},
  {"client_ref": "care-20261125", "kind": "care_list", "data": {"batch_id": "care-20261125",
     "entries": [{"customer_key": "a1b2…", "category_id": 2, "last_order_at": "2026-10-26 00:00:00", "due_date": "2026-11-25", "score": 0.9, "reason": "..."}]}}
]}
```

Phản hồi: `{"results": [{"client_ref": "...", "status": "accepted|rejected", "result": "content:42", "duplicate": true?, "error": "..."}]}`. Gửi lại cùng `client_ref` sẽ không tạo bản ghi trùng. Mọi nội dung nhận được đều vào trạng thái **chờ duyệt**.

### POST /api/sync/publish  — quyền `content:publish`

AI tự xuất bản **một** FAQ hoặc bài blog (ARCHITECTURE ADR-16 của `ai-company/`). Dùng khóa riêng, khác khóa `drafts:write`; thu hồi khóa này ở Quản trị → Khóa API là dừng ngay.

```json
{"client_ref": "co:01J…", "kind": "faq",
 "data": {"title": "...", "body": "...", "body_is_text": true, "meta_description": "...", "keywords": "...", "product_id": 5, "category_id": 1,
          "source_refs": [{"product_id": 5, "info_version": 3}], "generated_by": "co:content_agent"}}
```

Phản hồi: `{"content_id": 42, "kind": "faq", "status": "published", "published_at": "…", "url": "https://…/hoi-dap.html", "quota": {"used": 1, "limit": 3}}`.

Website kiểm lần cuối, theo thứ tự:
1. Gửi lại cùng `client_ref` (theo từng khóa) → trả bài đã đăng, kèm `"duplicate": true`, không đếm hạn mức.
2. `AI_PUBLISH_DISABLED` → `AI_PUBLISH_HOURS` → `AI_PUBLISH_QUOTA` (đếm theo ngày giờ Việt Nam, có khóa dòng nên gửi song song cũng không vượt).
3. `SOURCE_OUTDATED` khi `info_version` trong `source_refs` khác thông tin nhãn hiện tại.
4. Nội dung qua bộ lọc HTML danh sách trắng như bài nhân viên.

Bài có `source = 'ai'`, `published_by = 'ai'`. Audit `content.ai_publish` (người làm: `sync`). `/api/sync/feedback` báo `approved` cho `client_ref` này, `retracted` khi bị gỡ.

### POST /api/sync/unpublish  — quyền `content:publish`

```json
{"content_id": 42, "reason": "Owner bấm Gỡ bài trên Telegram"}
```

Hoặc dùng `client_ref` thay cho `content_id`. `reason` bắt buộc. Phản hồi như `publish`, `status` là `unpublished`. Gọi lại không lỗi.

Chỉ gỡ được bài do AI xuất bản: `content_id` của bài nhân viên → `FORBIDDEN` (403); không có → `NOT_FOUND` (404). Bản đã gỡ vẫn lưu ở Quản trị → Nội dung (trạng thái `unpublished`). Audit `content.ai_unpublish`.
