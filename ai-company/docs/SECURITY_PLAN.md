# SECURITY_PLAN: bảo mật, quyền hạn, tuân thủ

> Trạng thái: v0.1, chờ Owner duyệt. Các nội dung pháp lý dưới đây là **phân tích kỹ thuật**, không phải tư vấn pháp luật. Mục §6 cần luật sư rà soát (Q-L*).

## 1. Mô hình đe dọa

| Tài sản | Mối đe dọa | Nguồn |
|---|---|---|
| Khóa API (LLM, quảng cáo, website, Zalo) | Lộ khóa → bị tiêu tiền, bị chiếm tài khoản | Lộ trong log hoặc prompt, repo, máy bị xâm nhập |
| Ngân sách (LLM, quảng cáo) | Agent chạy vòng lặp hoặc bị dẫn dụ chi tiêu | Lỗi logic, prompt injection |
| Dữ liệu khách, lead | Lộ, dùng sai mục đích, chuyển ra nước ngoài trái luật | Gửi lên LLM, xuất file, agent bị dẫn dụ |
| Danh tiếng, pháp lý | Nội dung sai sự thật, quảng cáo công dụng chữa bệnh, spam | LLM bịa, kiến thức web sai |
| Tính toàn vẹn của bộ não | Kiến thức độc hại cài vào trí nhớ chung, agent tự nới quyền | Nội dung web, tài liệu tải lên, agent khác |
| Audit | Xóa dấu vết | Agent hoặc người dùng có quyền cao |

**Tác nhân giả định:**
1. Nội dung bên ngoài độc hại: trang web, bình luận, tin nhắn khách, PDF.
2. Agent bị dẫn dụ (coi như *người trong cuộc không đáng tin*).
3. Tài khoản người dùng bị lộ.
4. Lỗi cấu hình của chính chúng ta.

## 2. Ánh xạ 14 yêu cầu SRS §15 sang biện pháp

| # | Yêu cầu | Biện pháp |
|---|---|---|
| 1 | Authentication | Đăng nhập email + mật khẩu (Argon2id), TOTP 2FA **bắt buộc với Owner**, phiên HttpOnly/SameSite/Secure, khóa tạm sau 5 lần sai. GPU worker dùng token riêng có phạm vi hẹp |
| 2 | RBAC | Vai trò người dùng: `owner`, `manager`, `reviewer`, `viewer`. Quyền chi tiết theo màn hình và API |
| 3 | Agent Permission Control | Policy Engine mặc định từ chối, theo (agent × công cụ × hành động × cấp tự chủ × hạn mức) |
| 4 | API Key Encryption | Mã hóa phong bì: khóa dữ liệu AES-256-GCM cho từng secret, khóa chủ lấy từ biến môi trường hoặc KMS, có `key_version` để xoay khóa |
| 5 | Secret Management | Secret chỉ ở `secrets` (đã mã hóa) và `.env` trên máy chủ (không vào git). Tool Gateway giải mã ngay lúc gọi. **Secret không bao giờ vào ngữ cảnh LLM, log hay audit** |
| 6 | Audit Logging | `audit_logs` chỉ thêm + chuỗi băm; ghi mọi hành động có tác động, mọi phê duyệt, mọi thay đổi quyền và bộ não |
| 7 | Rate Limiting | API theo người dùng/IP; Model Gateway theo nhà cung cấp và agent; Tool Gateway theo công cụ; ngân sách USD theo agent/ngày |
| 8 | Input Validation | Pydantic cho mọi API; schema cho mọi đầu vào công cụ; giới hạn kích thước |
| 9 | Output Validation | Đầu ra LLM có cấu trúc được kiểm schema; nội dung xuất bản qua kiểm tra tất định (cụm cấm, giá khớp DB, link hợp lệ) |
| 10 | Prompt Injection Protection | §4 |
| 11 | File Upload Validation | Danh sách định dạng cho phép, kiểm tra magic bytes, giới hạn dung lượng, quét ClamAV (tùy chọn), không thực thi; PDF/Office chuyển sang văn bản trong sandbox |
| 12 | Database Backup | §8 |
| 13 | Data Isolation | RLS trên trí nhớ; `org_id` trên mọi bảng; vai trò CSDL tách biệt; agent không có kết nối CSDL |
| 14 | Human Approval | §3.2 |

## 3. Quyền hạn và phê duyệt

### 3.1. Policy Engine

```
authorize(principal, action, resource, context) -> Allow | RequireApproval(reason) | Deny(reason)
```

- Thứ tự quyết định: quy tắc cốt lõi (constitution) → danh sách bắt buộc người duyệt → quyền của agent (`agent_permissions`) → hạn mức (ngân sách, số lần/ngày) → ngữ cảnh (dữ liệu không tin cậy trong chuỗi suy luận? ngoài giờ cho phép?).
- Chính sách là **mã + dữ liệu**, có test. Agent không có công cụ nào ghi vào `agent_permissions`, `constitution` hay `tool_registry`. Các bảng này chỉ người dùng ghi được, qua API có 2FA và audit.
- Mỗi lần gọi đều ghi quyết định cùng lý do. Dashboard hiển thị được "vì sao agent bị chặn".

### 3.2. Hành động bắt buộc người duyệt

Không phụ thuộc cấp tự chủ: kể cả L4 cũng không bỏ qua được các hành động này.

| Hành động (SRS §13) | Ghi chú |
|---|---|
| Thay đổi giá sản phẩm | Nền tảng không có công cụ này. Chỉ đề xuất |
| Tăng ngân sách quảng cáo vượt ngưỡng | Ngưỡng do Owner đặt (Q-B2) |
| Thanh toán | Không có công cụ thanh toán trong v1 |
| Xóa dữ liệu | Chỉ người dùng |
| Gửi chiến dịch hàng loạt | Email, Zalo, tin nhắn tới ≥ N người |
| Thay đổi chính sách | |
| Xuất bản nội dung có rủi ro pháp lý | Do **cửa tuân thủ** (§6.3) phân loại |
| Thay đổi quyền hạn agent | |
| ➕ Liên hệ lần đầu với lead hoặc KOC | Rủi ro spam và dữ liệu cá nhân |
| ➕ Gửi bất kỳ tin nào trực tiếp cho khách | Ở v1, Customer Agent chỉ soạn nháp |
| ➕ Bật một tích hợp mới hoặc cấp OAuth | |
| ➕ Thăng hạng phiên bản bộ não | BRAIN_SPEC §9 |

Mỗi phê duyệt gắn với **digest của nội dung** cụ thể. Nội dung đổi sau khi duyệt thì phê duyệt mất hiệu lực. Phê duyệt có hạn (mặc định 72 giờ).

## 4. Chống prompt injection (SRS §5.3, §15)

Phòng thủ nhiều lớp. Không có lớp nào đủ một mình:

1. **Tách kênh.** Nội dung bên ngoài được bọc trong khối `<untrusted source=...>` và luôn được mô tả với model là *dữ liệu*. Prompt hệ thống nói rõ: chỉ thị trong dữ liệu không có hiệu lực.
2. **Đọc cách ly (mẫu hai LLM).** Trang web hay tài liệu được một lời gọi model **không có công cụ** đọc và trích ra JSON có schema hẹp (vd `{claims[], prices[], contacts_public[]}`). Agent chính chỉ thấy JSON đã kiểm schema, không thấy văn bản thô. Văn bản thô vẫn lưu ở object storage để truy vết.
3. **Theo dõi độ nhiễm (taint).** Nếu một bước kế hoạch được sinh *sau khi* agent đọc dữ liệu không tin cậy, mọi hành động có tác động ra ngoài trong bước đó tự động thành `RequireApproval`.
4. **Quyền tối thiểu.** Agent đọc web không có công cụ gửi tin hay chi tiền. Muốn hành động thì phải gửi `task_request` cho agent khác, và mọi task đều qua Policy Engine.
5. **Danh sách đích cho phép.** `web.fetch` có danh sách chặn (mạng nội bộ, IP riêng, metadata đám mây) để chống SSRF. Công cụ HTTP tự do không có trong v1.
6. **Bảo vệ trí nhớ.** Kiến thức từ nguồn ngoài vào `knowledge_candidates` với `source_trust=unverified_external`, qua thẩm định mới thành kiến thức. Một nguồn duy nhất không thể tự đưa mình vào shared knowledge.
7. **Kiểm thử tấn công liên tục** (TEST_PLAN ST-01…ST-12): bộ tình huống injection tiếng Việt và tiếng Anh, chạy trong CI với model giả và định kỳ với model thật.

## 5. Secret và dữ liệu nhạy cảm trong log

- Logger có bộ lọc: che chuỗi giống khóa API (`sk-…`, `xk_…`, JWT), SĐT Việt Nam, email, số tài khoản.
- `system_logs` và `task_logs` không lưu prompt đầy đủ theo mặc định, chỉ lưu digest + metadata. Chế độ debug lưu prompt (đã che) có hạn 7 ngày và cần Owner bật.
- Không ghi log nội dung "suy nghĩ nội bộ" do nhà cung cấp model trả về nếu điều khoản nhà cung cấp hạn chế (SRS §12.3).

## 6. Tuân thủ pháp lý (cần luật sư xác nhận)

### 6.1. Dữ liệu cá nhân (Luật 91/2025/QH15, NĐ 356/2025/NĐ-CP)
- **Tối thiểu hóa:** nền tảng mặc định chỉ nhận `customer_key` (như dịch vụ AI hiện tại). Tên, SĐT, địa chỉ nằm lại ở website.
- **Chuyển dữ liệu ra nước ngoài:** gửi nội dung có dữ liệu cá nhân cho LLM đặt máy chủ ở nước ngoài có thể phát sinh nghĩa vụ hồ sơ và thông báo. Mặc định `provider_registry.data_policy.may_receive_pii=false`: Model Gateway che SĐT, email, tên trước khi gửi, và **chặn** nếu phát hiện dữ liệu cá nhân sót lại. Cần luật sư xác nhận nghĩa vụ cụ thể (Q-L1).
- **Hồ sơ đánh giá tác động:** khả năng cao cần lập hồ sơ cho hoạt động xử lý dữ liệu khách bằng AI (Q-L2).
- **Quyền của chủ thể dữ liệu:** website đã có luồng xóa tài khoản. Nền tảng cần nghe sự kiện `customer.deleted` để xóa hoặc ẩn danh `customer_key` tương ứng trong trí nhớ (thêm sự kiện phía website ở Sprint 8).

### 6.2. Thu thập lead, KOC, đối tác
- Thông tin công khai trên mạng xã hội **vẫn là dữ liệu cá nhân**, và điều khoản của Facebook, TikTok, Shopee thường **cấm thu thập tự động**.
- Thiết kế v1:
  - chỉ dùng tìm kiếm web và trang công khai của *doanh nghiệp* (quán, đại lý, cửa hàng);
  - với cá nhân (KOC), chỉ dùng API chính thức hoặc danh sách Owner nhập tay;
  - lưu `lawful_basis`, `source_url`;
  - có hạn tự xóa;
  - liên hệ lần đầu bắt buộc người duyệt.
- Không xây công cụ vượt đăng nhập, vượt captcha hay scrape trái ToS.

### 6.3. Nội dung quảng cáo thực phẩm
- Sản phẩm là trà, bột ngũ cốc, bột thiên nhiên, cà phê. Quảng cáo thực phẩm **không được khẳng định công dụng phòng hay chữa bệnh**, và có thể phải tuân theo thủ tục riêng tùy loại sản phẩm (Q-L5).
- **Cửa tuân thủ** (Compliance Gate) là bước bắt buộc trước khi bất kỳ nội dung nào rời hệ thống:
  1. Từ điển cụm cấm/cụm rủi ro tiếng Việt (vd "chữa", "trị", "đặc trị", "thay thuốc", "giảm cân cấp tốc"…), kiểm tra tất định.
  2. Bộ phân loại rủi ro (model rẻ) phân loại nội dung.
  3. Rủi ro trung bình hoặc cao thì `RequireApproval`, kèm giải thích.

  Từ điển cụm cấm là `shared_knowledge` loại `policy`, chỉ Owner sửa.
- Tài nguyên hình ảnh/video do AI tạo được gắn cờ `ai_generated`. Owner quyết định có ghi chú công khai hay không (Q-L6).

### 6.4. Tài khoản quảng cáo và nền tảng
- Ở v1, mọi thao tác *ghi* lên tài khoản quảng cáo đều là nháp hoặc đề xuất. Chuyển sang L3 cần Owner duyệt từng công cụ và đặt trần chi tiêu.

## 7. Chuỗi cung ứng và hạ tầng

- Ghim phiên bản phụ thuộc (lockfile `uv`/`pip-tools`, `pnpm-lock`). Quét lỗ hổng (pip-audit, `pnpm audit`, Trivy cho image) trong CI.
- Image Docker tối giản, chạy user không phải root, hệ thống tệp chỉ đọc nếu được.
- Chỉ mở 443 ra ngoài (reverse proxy Caddy/Traefik có TLS tự động). Postgres và Redis không mở ra Internet.
- GPU worker không nhận kết nối vào, chỉ gọi ra VPS bằng token có phạm vi `gpu:pull`.
- Không agent nào có quyền sửa mã production (SRS §15). CI/CD chỉ do người kích hoạt.

## 8. Sao lưu và khôi phục

| Mục tiêu | Giá trị đề xuất |
|---|---|
| RPO (mất dữ liệu tối đa) | 15 phút (WAL archiving) / 24 giờ (bản dump ngày) |
| RTO (thời gian dựng lại) | 4 giờ |
| Lưu giữ | 14 bản ngày + 8 bản tuần + 12 bản tháng |
| Nơi lưu | Ngoài VPS (object storage khác vùng), mã hóa |
| Diễn tập | Khôi phục thử hằng tháng vào CSDL tạm, có ca kiểm thử tự động (TEST_PLAN IT-BK-01) |

Sau khi khôi phục, Task Engine quét các task `IN_PROGRESS` có lease hết hạn để chạy lại. Nhờ khóa chống trùng ở mọi công cụ có tác động, chạy lại không gây việc trùng.

## 9. Agent không được (SRS §15) và cách thực thi

| Cấm | Thực thi bằng |
|---|---|
| Tự nâng quyền | Không có công cụ ghi quyền; RLS + vai trò CSDL; audit |
| Đọc secret ngoài phạm vi | Secret không vào ngữ cảnh; Tool Gateway giải mã nội bộ; agent không có công cụ đọc secret |
| Tự sửa mã production | Không có công cụ git/deploy; Automation Agent chỉ bật/tắt workflow đã duyệt |
| Tự xóa lịch sử kiểm toán | Bảng chỉ thêm, không vai trò nào có DELETE, chuỗi băm kiểm tra hằng ngày |
| Tự thay đổi chính sách bảo mật | Constitution băm + ghim; Policy Engine chỉ đọc chính sách từ nguồn được Owner ký duyệt |
