# QUESTIONS_FOR_OWNER: câu hỏi cần Owner trả lời

> **Cập nhật 26/11/2026:** Owner đã trả lời một phần. Các câu có ✅ đã quyết; câu trả lời và hệ quả ghi ở `DECISIONS.md`. Câu hỏi mới phát sinh ở cuối tệp (§G).
>
> 🔴 = cần trả lời trước khi bắt đầu Sprint 0–1 · 🟡 = cần trước Sprint ghi trong ngoặc.
> Mỗi câu đều có **mặc định đề xuất**. Nếu Owner đồng ý với mặc định, chỉ cần ghi "đồng ý mặc định".

## A. Phạm vi và kiến trúc

**✅ Q-A1. AI có được tự xuất bản lên website không?**  
→ *Owner: tự xuất bản + báo Telegram.*
Hiện website chỉ nhận *bản nháp chờ duyệt* (AT-09); không có API xuất bản. SRS §6.2 có nói "tự xuất bản nếu đã được cấp quyền".
- *Mặc định đề xuất:* v1 giữ nguyên "chỉ bản nháp". Sau 3 tháng, Owner có thể bật L3 cho từng loại nội dung rủi ro thấp (vd FAQ giao hàng). Khi đó mới thêm API xuất bản có giới hạn ở website.

**✅ Q-A2. Mã nguồn để ở đâu?**  
→ *Owner: chạy trên máy cá nhân; repo xem Q-A2b.*
- (a) Repo riêng `ai-marketing-company`. Stack khác hẳn website (Docker, Postgres, Next.js), triển khai riêng.
- (b) Thư mục `ai-company/` trong `moctam-shop`, như bản thiết kế này đang đặt.
- *Mặc định đề xuất:* **(a)**. Owner tạo repo trống rồi gắn vào phiên làm việc, tài liệu sẽ được chuyển sang đó.

**✅ Q-A3. Nền tảng chạy ở đâu, ai quản trị máy chủ?**  
→ *Owner: Windows 11.*
- *Mặc định đề xuất:* VPS Linux 4 vCPU / 8–16 GB làm lõi. Máy có GPU làm worker tùy chọn (ARCHITECTURE §6). Owner cho biết: đã có VPS chưa (Hostinger VPS hay nơi khác), và ai sẽ cài đặt và cập nhật.

## B. Ngân sách

**✅ Q-B1. Trần chi phí LLM mỗi ngày và mỗi tháng (USD) là bao nhiêu?**  
→ *Owner: 50 USD, cần làm rõ ngày hay tháng (Q-B1a).*
Đây là chi phí vận hành lớn nhất (ARCHITECTURE §8.2). Khi chạm trần, hệ thống hạ việc ưu tiên thấp xuống model rẻ hoặc hoãn sang hôm sau.
- *Mặc định đề xuất:* bắt đầu với trần thấp trong 2 tuần chạy thử ở Sprint 4, đo chi phí thật rồi điều chỉnh. Owner cho con số ban đầu.

**🟡 (Sprint 4) Q-B2. Ngưỡng ngân sách quảng cáo cần người duyệt.**
Owner đã có tài khoản quảng cáo đang chạy chưa? Mức tăng hoặc giảm ngân sách bao nhiêu thì bắt buộc duyệt?
- *Mặc định:* mọi thay đổi ngân sách đều cần duyệt trong v1.

## C. Công nghệ

**✅ Q-T1. LangGraph (SRS) hay điều phối tự xây (ADR-05)?**  
→ *Owner: LangGraph.*
- *Mặc định đề xuất:* tự xây phần điều phối tổ chức trên Postgres. LangGraph là bộ chạy tùy chọn cho từng agent. Nếu Owner muốn bám đúng SRS, đội vẫn làm được, nhưng sẽ phải đồng bộ hai nguồn trạng thái.

**✅ Q-T2. Nhà cung cấp LLM nào dùng trước, đã có tài khoản và khóa API chưa?**  
→ *Owner: Claude + ChatGPT.*
- *Mặc định đề xuất:* một nhà cung cấp đám mây chính cho lập luận và viết tiếng Việt, cộng model rẻ cho phân loại. Gateway hỗ trợ Anthropic, OpenAI-compatible và Google; đổi nhà cung cấp chỉ cần sửa cấu hình.

**✅ Q-T3. Thông số máy GPU.**  
→ *Owner: i5-11400F, còn thiếu card đồ họa và RAM (Q-T3a).*
Cần biết: GPU gì, bao nhiêu VRAM, hệ điều hành, thường bật bao nhiêu giờ mỗi ngày. Thông tin này quyết định model cục bộ nào chạy được (embedding, phân loại, soạn nháp rẻ).

**🟡 (Sprint 0) Q-T4. Chấp nhận các giấy phép không phải MIT/Apache không?**
Gồm: psycopg (LGPL), Dramatiq (LGPL), n8n (Sustainable Use License, nếu bật sau), và Redis bản mới hay Valkey.
- *Mặc định:* chấp nhận LGPL (dùng như thư viện); chọn Valkey; n8n để sau.

## D. Tổ chức và vận hành

**🔴 Q-O1. Ai duyệt việc của AI?**
Chỉ Owner, hay có nhân viên được giao duyệt nội dung, quảng cáo, chăm sóc khách? Mỗi người duyệt được bao nhiêu mục mỗi ngày? Con số này quyết định "sức duyệt", tức số bản nháp tối đa đang chờ.

**✅ Q-O2. Phòng Công nghệ & Dữ liệu (Web CRO, Data Analyst, Automation) báo cáo cho ai?**  
→ *Owner: báo cáo qua Telegram.*
SRS không nói rõ.
- *Mặc định:* báo cáo chuyên môn cho Growth Director; CEO giao trực tiếp khi cần.

**✅ Q-O3. Đã có Brand Guidelines chưa?**  
→ *Owner: Claude tự thiết kế.*
Gồm logo, màu, font, giọng văn, hình mẫu. Creative Agent bắt buộc phải có thư viện này (SRS §3.2). Nếu chưa có, Sprint 6 sẽ có bước soạn bản nháp brand guidelines để Owner duyệt.

**✅ Q-O4. 90 ngày đầu, ưu tiên mục tiêu nào trong 12 mục tiêu SRS §1.2?**  
→ *Owner: đồng ý mặc định.*
Thứ tự này quyết định trọng số mục tiêu của CEO và thứ tự tích hợp ở Sprint 8.
- *Mặc định đề xuất:* (1) SEO + nội dung website → (2) chăm sóc khách cũ → (3) Facebook/TikTok → (4) khách sỉ/đại lý → (5) quảng cáo.

## E. Tích hợp (trước Sprint 8; Sprint 6–7 cần một phần)

Owner đánh dấu những tài khoản **đang có** và tích hợp **muốn bật trước**. Tích hợp nào chưa đủ điều kiện API thì hệ thống hiện "chưa kết nối" và không giả lập số liệu.

| Mã | Tích hợp | Câu hỏi |
|---|---|---|
| Q-I1 | Google Analytics 4, Search Console | Website đã gắn chưa? Ai có quyền quản trị? |
| Q-I2 | Google Ads, Meta Ads, TikTok Ads | Có tài khoản nào? Mức chi hiện tại? |
| Q-I3 | Shopee, TikTok Shop | Có gian hàng chưa? Các nền tảng này thường đòi đăng ký làm đối tác (partner) mới cấp API |
| Q-I4 | CRM, email marketing | Đang dùng công cụ nào, hay dùng dữ liệu khách trên website? |
| Q-I5 | Zalo OA | Có Official Account chưa? Dùng để chăm sóc khách hay chỉ thông báo? |
| Q-I6 | Tạo ảnh/video | Dùng dịch vụ nào (đám mây hay chạy trên GPU nhà)? Ngân sách? |

## F. Pháp lý (cần luật sư; xem SECURITY_PLAN §6)

**✅ Q-L1. Phạm vi dữ liệu khách mà nền tảng được xử lý.**  
→ *Owner: đồng ý mặc định.*
- *Mặc định đề xuất:* chỉ dùng mã ẩn danh như hiện nay. Customer Agent chỉ soạn câu trả lời; nhân viên gửi từ kênh của xưởng. Không gửi dữ liệu cá nhân cho LLM ở nước ngoài.
- Nếu Owner muốn AI trực tiếp trò chuyện với khách, cần luật sư tư vấn trước về chuyển dữ liệu ra nước ngoài và về sự đồng ý của khách.

**🟡 (Sprint 7) Q-L2. Lập hồ sơ đánh giá tác động xử lý dữ liệu cá nhân.**
Ai lập, có thuê luật sư không? Website đã có trang Chính sách bảo mật theo Luật 91/2025; nền tảng AI cần được bổ sung vào đó.

**🟡 (Sprint 7) Q-L3. Chính sách tìm lead và KOC.**
Đồng ý với giới hạn ở SECURITY_PLAN §6.2 không? Gồm:
- chỉ nguồn công khai, đúng điều khoản nền tảng;
- không scrape mạng xã hội;
- liên hệ lần đầu cần duyệt;
- xóa lead không dùng sau 180 ngày.

**🟡 (Sprint 9) Q-L4. Thời gian lưu nhật ký kiểm toán và log.**
- *Mặc định:* audit ≥ 2 năm; log vận hành 13 tháng.

**🟡 (Sprint 5) Q-L5. Phân loại sản phẩm và quy định quảng cáo.**
Sản phẩm là thực phẩm thông thường, hay có sản phẩm thuộc nhóm phải xác nhận nội dung quảng cáo? Có danh sách công dụng **được phép** nói (đã có căn cứ, giấy tờ) không? Danh sách này là nền của Compliance Gate.

**🟡 (Sprint 6) Q-L6. Có ghi chú công khai "hình ảnh/video do AI tạo" không?**
- *Mặc định:* có gắn nhãn nội bộ; Owner quyết định việc ghi chú công khai.

## G. Câu hỏi mới (phát sinh từ câu trả lời ngày 26/11/2026)

**🔴 Q-B1a. 50 USD là trần mỗi ngày hay mỗi tháng?**
Hai cách hiểu chênh nhau 30 lần (ARCHITECTURE §8.3).
- *Mặc định:* 50 USD/tháng.

**🔴 Q-T3a. Máy có card đồ họa gì (tên, VRAM), bao nhiêu RAM, ổ đĩa còn trống bao nhiêu?**
i5-11400F không có đồ họa tích hợp nên chắc chắn có card rời. Card 8 GB VRAM trở lên chạy được model nhỏ cục bộ (phân loại, embedding). RAM nên từ 16 GB, tốt nhất 32 GB, vì Docker + Postgres + trình duyệt cùng chạy.
- *Mặc định:* không chạy LLM cục bộ.

**🔴 Q-A1a. AI được tự xuất bản những gì, bao nhiêu, lúc nào?**
- *Mặc định:* FAQ và blog; tối đa 1 blog + 3 FAQ mỗi ngày; chỉ 8:00–21:00. Chủ đề sức khỏe, dị ứng, giá, khuyến mãi, pháp lý luôn chờ Owner bấm duyệt trên Telegram.
- Lý do giới hạn: Google có chính sách chống nội dung hàng loạt kém chất lượng, nên đăng quá nhiều bài AI một lúc có thể làm hại SEO.

**🔴 Q-TG1. Telegram.**
Owner mở @BotFather, tạo bot, giữ *token* (sẽ nhập vào máy lúc cài đặt, không gửi qua chat). Owner muốn nhận tin nhắn riêng hay trong một nhóm (vd có cả nhân viên)?
- *Mặc định:* nhắn riêng cho một tài khoản Owner.

**🟡 (Sprint 0) Q-A2b. Mã nguồn giữ trong repo `moctam-shop` hay tạo repo riêng?**
- *Mặc định:* giữ trong `moctam-shop/ai-company/`.

**🟡 (Sprint 1) Q-W1. Máy bật những giờ nào trong ngày? Có bộ lưu điện (UPS) không?**
Lịch chạy của các agent sẽ dồn vào giờ máy bật.
- *Mặc định:* 8:00–22:00, không có UPS.

