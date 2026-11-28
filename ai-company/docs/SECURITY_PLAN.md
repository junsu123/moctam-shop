# SECURITY_PLAN: bảo mật, quyền hạn, tuân thủ

> Trạng thái: v0.2 (26/11/2026, theo `DECISIONS.md`), chờ Owner duyệt. Owner quyết định bỏ qua phần pháp lý; §6 chỉ còn các biện pháp kỹ thuật và vận hành.

## 1. Mô hình đe dọa

| Tài sản | Mối đe dọa | Nguồn |
|---|---|---|
| Khóa API (LLM, quảng cáo, website, Zalo) | Lộ khóa → bị tiêu tiền, bị chiếm tài khoản | Lộ trong log hoặc prompt, repo, máy bị xâm nhập |
| Ngân sách (LLM, quảng cáo) | Agent chạy vòng lặp hoặc bị dẫn dụ chi tiêu | Lỗi logic, prompt injection |
| Dữ liệu khách, lead | Lộ, dùng sai mục đích, chuyển ra nước ngoài trái luật | Gửi lên LLM, xuất file, agent bị dẫn dụ |
| Danh tiếng | Nội dung sai sự thật, nói công dụng chữa bệnh, spam | LLM bịa, kiến thức web sai |
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
| 1 | Authentication | Đăng nhập email + mật khẩu (Argon2id), TOTP 2FA **bắt buộc với Owner**, phiên HttpOnly/SameSite/Secure, khóa tạm sau 5 lần sai. Telegram: chỉ nhận lệnh từ chat ID đã đăng ký, nút có chữ ký (§3.4) |
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
| Xuất bản nội dung có rủi ro (SRS) | Do **Content Gate** (§6.3) phân loại. FAQ/blog *không* rủi ro được tự xuất bản theo §3.3 |
| Thay đổi quyền hạn agent | |
| ➕ Liên hệ lần đầu với lead hoặc KOC | Rủi ro spam và dữ liệu cá nhân |
| ➕ Gửi bất kỳ tin nào trực tiếp cho khách | Ở v1, Customer Agent chỉ soạn nháp |
| ➕ Bật một tích hợp mới hoặc cấp OAuth | |
| ➕ Thăng hạng phiên bản bộ não | BRAIN_SPEC §9 |

Mỗi phê duyệt gắn với **digest của nội dung** cụ thể. Nội dung đổi sau khi duyệt thì phê duyệt mất hiệu lực. Phê duyệt có hạn (mặc định 72 giờ).

**Duyệt ở đâu (v0.2):**

| Mức rủi ro | Kênh duyệt | Ví dụ |
|---|---|---|
| Thấp, trung bình | Nút trên **Telegram** hoặc dashboard | Bài thuộc chủ đề chỉ-người-duyệt, liên hệ lead, gửi danh sách chăm sóc |
| Cao | **Chỉ dashboard + 2FA**. Telegram chỉ gửi link | Đổi quyền agent, thăng hạng bộ não, tăng ngân sách, gửi tin hàng loạt, bật tích hợp mới, xóa dữ liệu |

Owner không trả lời **không** được coi là đồng ý: việc chờ duyệt hết hạn thì tự hủy.

### 3.3. Tự xuất bản FAQ/blog (Q-A1, ARCHITECTURE ADR-16)

| Kiểm soát | Chi tiết |
|---|---|
| Khóa riêng | `content:publish`: khác khóa đọc và khóa gửi bản nháp; chỉ áp cho nội dung `source='ai'`; thu hồi được ngay trên website |
| Năm lớp chặn | Content Gate → review của Marketing Director → chủ đề chỉ-người-duyệt → hạn mức ngày và khung giờ → website kiểm tra lần cuối (hạn mức đếm ở phía website) |
| Gỡ ngay | Nút **Gỡ bài** trên Telegram và dashboard gọi `unpublish`; bản gỡ được lưu lại |
| Công tắc tắt | `/tamdung xuatban` trên Telegram, hoặc thu hồi khóa trên website, là dừng toàn bộ việc tự xuất bản |
| Nới dần | Hạn mức chỉ tăng khi Owner đồng ý, dựa trên tỉ lệ bài không bị gỡ trong 30 ngày |

### 3.4. Telegram

- Owner **dán token bot trong dashboard** (*Cài đặt → Telegram*). Hệ thống kiểm tra bằng `getMe`, mã hóa vào kho secret (§5), và chỉ hiển thị 4 ký tự cuối. Không lưu trong mã, `.env` hay git; không gửi qua chat.
- Kết nối chat bằng **mã 6 số** hiện trên dashboard (hiệu lực 10 phút, dùng một lần), không bằng cách gõ chat ID. Đổi token hoặc thêm chat có quyền duyệt cần **mật khẩu + 2FA**, và có ghi audit.
- Chỉ xử lý tin nhắn và nút bấm từ **chat ID trong danh sách** `telegram_chats`. Tin từ nơi khác bị bỏ qua và ghi audit.
- Dữ liệu của nút (`callback_data`) gồm: mã hành động + ID đối tượng + digest + hạn dùng, ký HMAC. Mỗi nút dùng được một lần.
- **Không gửi** dữ liệu cá nhân của khách, giá vốn hay secret qua Telegram. Báo cáo chỉ có số tổng hợp.
- Bot dùng long-polling, nên máy Owner không mở cổng nào.

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

## 6. An toàn nội dung và dữ liệu

> v0.2: Owner quyết định **bỏ qua phần pháp lý** (26/11/2026): không có bước rà soát luật sư, không có câu hỏi pháp lý chặn Sprint. Các biện pháp dưới đây được giữ lại vì lý do **kỹ thuật và vận hành**: chống bịa nội dung, chống bị khóa tài khoản nền tảng, bảo mật dữ liệu. Không phải vì nghĩa vụ pháp lý.

### 6.1. Dữ liệu khách
- **Tối thiểu hóa** (Owner đồng ý ở Q-L1): nền tảng chỉ nhận `customer_key`. Tên, SĐT, địa chỉ nằm lại ở website. Lộ máy cá nhân thì cũng không lộ danh sách khách.
- Model Gateway che SĐT, email, tên trước khi gửi cho LLM, và **chặn** nếu phát hiện dữ liệu cá nhân sót lại (`provider_registry.data_policy.may_receive_pii=false`).
- Khi khách xóa tài khoản trên website (luồng đã có), nền tảng nghe sự kiện `customer.deleted` và xóa `customer_key` tương ứng trong trí nhớ (thêm sự kiện phía website ở Sprint 8).

### 6.2. Thu thập lead, KOC, đối tác
- Facebook, TikTok, Shopee thường chặn hoặc khóa tài khoản khi phát hiện thu thập tự động. Thiết kế v1:
  - chỉ dùng tìm kiếm web và trang công khai của *doanh nghiệp* (quán, đại lý, cửa hàng);
  - với cá nhân (KOC), chỉ dùng API chính thức hoặc danh sách Owner nhập tay;
  - mỗi dòng lưu `source_url`;
  - lead không dùng tự xóa sau 180 ngày, để danh sách gọn và mới;
  - liên hệ lần đầu bắt buộc người duyệt, để tránh bị đánh dấu spam.
- Không xây công cụ vượt đăng nhập hay vượt captcha.

### 6.3. Cửa kiểm tra nội dung (Content Gate)
Đây là bước bắt buộc trước khi nội dung rời hệ thống, nhất là khi **AI tự xuất bản** (ADR-16). Mục đích: không đăng thông tin sai về sản phẩm. Ngoài ra, nền tảng quảng cáo (Meta, Google, TikTok) cũng hay từ chối nội dung nói công dụng chữa bệnh.
1. **Từ điển cụm rủi ro** tiếng Việt (vd "chữa", "trị", "đặc trị", "thay thuốc", "giảm cân cấp tốc", "cam kết 100%"…), kiểm tra tất định. Từ điển là cài đặt `content_gate` (*Sprint 4b*; thiết kế ban đầu là `shared_knowledge` loại `policy`), chỉ Owner sửa trong *Xuất bản → Content Gate*, mỗi lần sửa ghi audit. So nguyên cụm có dấu; cụm từ hai chữ trở lên thì viết không dấu cũng bị bắt.
2. **Đối chiếu với dữ liệu website**: giá, thành phần, quy cách, khuyến mãi nêu trong bài phải khớp `catalog`; không khớp thì chặn. *Sprint 4b*: đã đối chiếu giá (`list_price`); khuyến mãi luôn cần Owner duyệt; thành phần và quy cách chờ website có dữ liệu có cấu trúc.
3. **Bộ phân loại rủi ro** (model rẻ) đánh giá phần còn lại. Rủi ro trung bình hoặc cao thì `RequireApproval` qua Telegram, kèm giải thích. Bộ phân loại lỗi thì coi là "chưa rõ" và cũng cần duyệt.

Tài nguyên ảnh/video do AI tạo được gắn cờ nội bộ `ai_generated`. Mặc định không ghi chú công khai.

### 6.4. Tài khoản quảng cáo và nền tảng
- Ở v1, mọi thao tác *ghi* lên tài khoản quảng cáo đều là nháp hoặc đề xuất. Chuyển sang L3 cần Owner duyệt từng công cụ và đặt trần chi tiêu.

## 7. Chuỗi cung ứng và hạ tầng

- Ghim phiên bản phụ thuộc (lockfile `uv`/`pip-tools`, `pnpm-lock`). Quét lỗ hổng (pip-audit, `pnpm audit`, Trivy cho image) trong CI.
- Image Docker tối giản, chạy user không phải root, hệ thống tệp chỉ đọc nếu được.
- Chỉ mở 443 ra ngoài (reverse proxy Caddy/Traefik có TLS tự động). Postgres và Redis không mở ra Internet.
- **Máy Windows 11 của Owner (v0.2):**
  - bật **BitLocker** cho ổ chứa dữ liệu;
  - tài khoản Windows có mật khẩu/PIN, khóa màn hình tự động;
  - Windows Defender bật;
  - Docker chỉ mở cổng trên `127.0.0.1` (Postgres, Redis, API, dashboard không lộ ra mạng LAN);
  - không chạy container ở chế độ privileged;
  - tệp `.env` chỉ tài khoản Owner đọc được.
- Không agent nào có quyền sửa mã production (SRS §15). CI/CD chỉ do người kích hoạt.

## 8. Sao lưu và khôi phục

| Mục tiêu | Giá trị đề xuất |
|---|---|
| RPO (mất dữ liệu tối đa) | 24 giờ (bản dump ngày). Có thể bật WAL archiving ra ổ ngoài để còn 15 phút |
| RTO (thời gian dựng lại) | 4 giờ |
| Lưu giữ | 14 bản ngày + 8 bản tuần + 12 bản tháng |
| Nơi lưu | **Ngoài máy**: ổ cứng ngoài + thư mục đám mây (OneDrive/Google Drive), mã hóa trước khi chép |
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
