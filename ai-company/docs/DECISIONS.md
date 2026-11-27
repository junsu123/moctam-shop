# DECISIONS: sổ quyết định của Owner

> Ghi lại câu trả lời của Owner cho `QUESTIONS_FOR_OWNER.md` và hệ quả kỹ thuật của từng câu.
> Lần 1: 26/11/2026 (21:34). Lần 2: 21:48 (bỏ qua pháp lý). Lần 3: 21:53. Tài liệu thiết kế được cập nhật lên **v0.2** theo sổ này.
> Kiến trúc **vẫn chờ Owner ghi "duyệt kiến trúc"** trước khi viết mã (CLAUDE.md).

## 1. Đã quyết

| Mã | Owner trả lời | Quyết định kỹ thuật | Hệ quả chính | Tài liệu đổi |
|---|---|---|---|---|
| Q-A1 | AI **tự xuất bản** lên website và báo qua **Telegram** (vd viết bài mới thì gửi link) | `site.publish` ở cấp L3 cho FAQ và blog, với 5 lớp chặn: Content Gate, Marketing Director review, chủ đề "chỉ người duyệt", hạn mức bài/ngày, nút **Gỡ bài** trên Telegram. Website thêm API `publish`/`unpublish` dùng khóa riêng | Đổi nguyên tắc AT-09 của website ("AI chỉ gửi bản nháp"): AI được xuất bản qua khóa riêng, có audit và gỡ được. Sửa ca kiểm thử website tương ứng | ARCH ADR-16, SECURITY §3.3, AGENT §3, TEST §6, PLAN Sprint 4 |
| Q-A2 | Mã nguồn chạy trên **máy tính cá nhân cấu hình khỏe** | Nền tảng chạy trên máy cá nhân, không thuê VPS. *Repo*: chưa trả lời, nên tạm giữ trong `moctam-shop/ai-company/` (tách repo sau vẫn được) | Máy tắt thì công ty AI nghỉ; website vẫn bán bình thường; bật lại thì làm bù | ARCH §6, ADR-01 |
| Q-A3 | **Windows 11** | Docker Desktop (backend WSL2) chạy Postgres + pgvector, Redis, worker. Ứng dụng tự khởi động cùng Windows; tắt chế độ ngủ trong giờ làm việc | Thêm hướng dẫn cài đặt Windows, sao lưu ra ổ ngoài hoặc đám mây, kiểm thử khởi động lại máy | ARCH §6, SECURITY §7–8, TEST IT-WIN-* |
| Q-B1 | Trần chi phí LLM **50 USD** | Tạm hiểu là **50 USD/tháng** (cách hiểu an toàn hơn), tức trần ngày ≈ 1,67 USD, cho phép một ngày vượt tối đa 3 USD nếu tháng còn dư. **Cần Owner xác nhận** (Q-B1a) | 50 USD/tháng là đủ nếu 85–90% lượt gọi dùng model rẻ (ARCH §8). Tạo video gần như phải có ngân sách riêng | ARCH §8, PLAN |
| Q-T1 | **LangGraph** (theo SRS) | LangGraph là bộ chạy luồng công việc của agent và của tổ chức, lưu checkpoint vào Postgres. Bảng `tasks` là góc nhìn nghiệp vụ, đồng bộ bằng các nút đồ thị chạy được nhiều lần mà không sinh tác động trùng (idempotent). Duyệt của người = `interrupt()` + tiếp tục khi Owner bấm nút trên Telegram | Có hai nơi lưu trạng thái, nên cần quy tắc đối soát (ADR-05 v0.2) | ARCH ADR-05, DB §6, TEST IT-LG-* |
| Q-T2 | **Claude** và **ChatGPT** | Làm adapter Anthropic + OpenAI trước; Google, Ollama, vLLM sau. Claude là nhà cung cấp chính; OpenAI làm dự phòng, làm *giám khảo khác họ* để chấm bài do Claude viết, và cung cấp embedding | Có hai họ model nên đánh giá độc lập chéo được (BRAIN_SPEC §8) | ARCH ADR-06, §8 |
| Q-T3 | **Intel Core i5-11400F** (6 nhân 12 luồng) | CPU đủ chạy Docker, Postgres, worker. Dòng "F" **không có đồ họa tích hợp**, nên máy phải có card rời; chưa rõ loại nào. **Chưa bật LLM cục bộ** cho tới khi biết card và RAM (Q-T3a) | Mọi lời gọi LLM tạm thời đi qua đám mây; embedding qua OpenAI hoặc model nhỏ chạy trên CPU | ARCH ADR-01, §8 |
| Q-O1 | (không trả lời trực tiếp; suy ra từ Q-A1 và Q-O2) | **Owner là người duyệt duy nhất, qua Telegram.** Việc rủi ro cao (quyền, ngân sách, thăng hạng bộ não) phải duyệt trên dashboard có 2FA | "Sức duyệt" = sức của một người; hạn mức bài tự xuất bản/ngày giữ ở mức thấp | SECURITY §3.2 |
| Q-O2 | Phòng Công nghệ & Dữ liệu **báo cáo qua Telegram** | Telegram là kênh của Owner: báo cáo, cảnh báo, link bài mới, nút duyệt/gỡ. Về chuyên môn, phòng này vẫn chịu sự điều phối của Growth Director (mặc định) | Thêm thành phần **Telegram Gateway** (ADR-15) | ARCH ADR-15, AGENT §2 |
| Q-O3 | **Claude tự thiết kế** Brand Guidelines | Sprint 4 Claude soạn *giọng văn* (cần ngay vì AI tự xuất bản); Sprint 6 soạn *nhận diện hình ảnh* (màu, font, logo, mẫu ảnh) dựa trên giao diện website hiện tại. Cả hai đều cần Owner duyệt một lần | Brand guidelines nằm trong shared knowledge loại `policy` | PLAN Sprint 4, 6 |
| Q-O4 | Đồng ý thứ tự mặc định: SEO + nội dung → chăm sóc khách cũ → Facebook/TikTok → khách sỉ/đại lý → quảng cáo | Trọng số mục tiêu ban đầu của AI CEO và thứ tự tích hợp theo đúng thứ tự này | Ads và Social để cuối; Sprint 8 ưu tiên GSC/GA4 | AGENT §4, PLAN |
| Q-L1 | Đồng ý mặc định: chỉ mã ẩn danh; Customer Agent chỉ soạn nháp; không gửi dữ liệu cá nhân cho LLM nước ngoài | Giữ P6 | Telegram cũng **không** được nhận dữ liệu cá nhân của khách | SECURITY §6.1 |
| Q-L2…L6 | **"Phần pháp lý bỏ qua"** (21:48) | Đóng toàn bộ câu hỏi pháp lý. Không có bước rà soát luật sư; không có mục pháp lý chặn Sprint. Áp mặc định kỹ thuật: lead tự xóa sau 180 ngày; audit giữ ≥ 2 năm; ảnh AI chỉ gắn nhãn nội bộ. **Giữ** Content Gate (chống đăng thông tin sai về sản phẩm), ẩn danh dữ liệu khách, không scrape, vì đây là biện pháp chất lượng, bảo mật và chống khóa tài khoản | Owner tự chịu trách nhiệm về khía cạnh pháp lý | SECURITY §6, ARCH §1/R4, PLAN |

### Lần 3 (21:53)

| Mã | Owner trả lời | Quyết định kỹ thuật | Tài liệu đổi |
|---|---|---|---|
| (3 biện pháp) | **Đồng ý giữ** Content Gate, ẩn danh dữ liệu khách, không scrape | Giữ nguyên SECURITY §6 | — |
| Q-B1a | **50 USD/tháng** | Phương án B (~42 USD/tháng): trần ngày 1,67 USD, một ngày tối đa 3 USD; cảnh báo ở 80%; Opus tắt mặc định | ARCH §8.3 |
| Q-T3a | **AMD Radeon RX 560, RAM 16 GB** | Không chạy LLM cục bộ (RX 560 không được Ollama/ROCm hỗ trợ; VRAM nhỏ). Embedding qua OpenAI. Cả hệ thống giới hạn 6 GB RAM trong WSL2, 2 worker. Khuyến nghị nâng 32 GB khi mở rộng | ARCH §6, ADR-06, R12; TEST PT-06 |
| Q-A1a | **Claude chỉ định** cách đăng hợp lý, chọn giờ vàng | Lịch 3 giai đoạn tăng dần: blog 19:30 (Thứ Ba/Thứ Bảy → thêm Thứ Năm → tối đa mỗi ngày); FAQ 11:30 → thêm 7:30, 17:30. Không đăng ngoài 7:00–21:30; cách nhau ≥ 3 giờ. Tự lùi giai đoạn khi Owner gỡ ≥ 2 bài/7 ngày. Sau 4 tuần, giờ vàng tính lại từ dữ liệu thật của xưởng | ARCH ADR-16, DB `publication_queue`, TEST IT-PUB-06/07 |
| Q-TG1 | **Đã có bot**; Owner **tự cập nhật trong trang quản trị** | Trang *Cài đặt → Telegram* trong dashboard: dán token (kiểm tra `getMe`, lưu mã hóa), kết nối chat bằng mã 6 số (`/ketnoi`), vai trò từng chat, bật/tắt loại tin, giờ yên lặng, gửi thử, đổi token. Thao tác nhạy cảm cần mật khẩu + 2FA | ARCH ADR-15, SECURITY §3.4, DB, TEST IT-TG-05 |

### Lần 4 (22:32): màn hình theo dõi

| Yêu cầu của Owner | Quyết định kỹ thuật | Tài liệu đổi |
|---|---|---|
| "Một màn hình hiển thị tất cả diễn biến đang diễn ra trên phần mềm, từng công việc của từng agent đang làm" | (1) **Làm ngay cho Văn phòng AI hiện tại** (`ai/`): `python -m xuong_ai monitor`, tự mở cùng `run` tại http://127.0.0.1:8765. Nội dung: làn hoạt động 60 phút theo nhân viên, bảng nhân viên, việc chờ + lý do, việc cần Owner, dòng diễn biến 2 giây. (2) **Đưa vào AI Company** thành màn hình **"Diễn biến trực tiếp"** của dashboard, làm từ Sprint 4 (lát cắt dọc). Mở rộng cho 15 agent: làn theo phòng ban, thu gọn/mở rộng, xem bước trong đồ thị LangGraph đang chạy, chi phí theo agent | ARCH §4 (Dashboard), PLAN Sprint 4/8, TEST E2E-LIVE |

### Lần 5 (22:43): duyệt kiến trúc

| Owner | Quyết định | Tài liệu đổi |
|---|---|---|
| "**duyệt kiến trúc** trang quản trị trọn gói" | Kiến trúc v0.2 **được duyệt**; bắt đầu Sprint 0. **Trang quản trị trọn gói (Control Center) đưa lên sớm:** Sprint 1 đã có trang dùng được (đăng nhập + 2FA, Cài đặt → Telegram, ngân sách, danh sách agent với tạm dừng/chạy lại, màn hình diễn biến). Mỗi Sprint sau bổ sung màn hình cho phần vừa làm, thay vì dồn hết dashboard vào Sprint 8 | CLAUDE.md, PLAN §3 |

### Ghi chú kỹ thuật Sprint 1 (không cần Owner quyết)

| Điểm | Quyết định | Lý do |
|---|---|---|
| Thư viện Telegram | httpx gọi thẳng Bot API thay cho aiogram | Chỉ cần `getMe`, `sendMessage`, `getUpdates`. Ít phụ thuộc, ít RAM (~60 MB), dễ giả lập khi test |
| OpenTelemetry | Chuyển sang Sprint 2 | Log JSON có request-id và sổ `model_usage` đã đủ cho Sprint 1. OTel cần khi có worker agent |
| Nhật ký không sửa được (IT-DB-03) | Trigger chặn UPDATE/DELETE/TRUNCATE + chuỗi băm SHA-256, `python -m app.cli verify-audit` | Chặn được cả tài khoản quản trị CSDL; nếu ai tắt trigger để sửa thì chuỗi băm vẫn lộ |
| Ghi sổ ngoài giao dịch request | Chi phí LLM, cảnh báo ngân sách, bộ đếm đăng nhập sai | Lỗi trả về rollback giao dịch chính, nhưng tiền đã tiêu và lần đăng nhập sai vẫn phải được ghi |
| TypeScript | Ghim 6.0 | `typescript-eslint` chưa hỗ trợ TS 7 |

### Ghi chú kỹ thuật Sprint 2 (không cần Owner quyết)

| Điểm | Quyết định | Lý do |
|---|---|---|
| Nạp bộ não lần đầu | Tự ghim hash quy tắc cốt lõi (`bootstrap`) | Bundle trong git đã qua review PR; mọi thay đổi sau đó cần Owner duyệt trên dashboard (rủi ro cao, 2FA) |
| Quyền công cụ | Chỉ lấy từ `tools/tool_permissions.yaml` của bộ não đang chạy; dashboard chỉ xem | Đổi quyền = đổi bộ não = qua duyệt; không có đường ghi quyền nào khác (SECURITY_PLAN §3.1) |
| Danh tính, kỹ năng | Đọc từ bộ não, chưa tạo `agent_profiles`, `agent_skills` | Một nguồn sự thật; kỹ năng gắn procedural memory ở Sprint 3/5 |
| Thứ tự Policy Engine | Danh sách bắt buộc duyệt xét **sau** quyền và hạn mức | Agent không có quyền thì bị chặn hẳn, không biến thành "xin duyệt"; có quyền (kể cả L4) thì vẫn phải duyệt |
| Công cụ chưa có tích hợp | Khai báo đủ 30 công cụ, chưa kết nối thì trả `NOT_CONFIGURED` | Quyền và chính sách kiểm được ngay; không có dữ liệu giả (CLAUDE.md quy tắc 5) |

## 2. Còn mở

| Mã | Câu hỏi | Mặc định nếu Owner không trả lời |
|---|---|---|
| Q-A2b | Giữ mã trong repo `moctam-shop` hay tạo repo riêng? | Giữ trong `moctam-shop/ai-company/` |
| Q-W1 | Máy bật những giờ nào? Có UPS (bộ lưu điện) không? | 7:00–22:00 (bao trùm các giờ đăng bài), không có UPS |
| Q-B2, Q-T4, Q-I1…I6 | Như `QUESTIONS_FOR_OWNER.md` | Như mặc định đã ghi ở đó |
