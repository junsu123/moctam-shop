# AI Marketing Company Platform

Nền tảng nhiều agent AI vận hành như một công ty marketing cho xưởng: có AI CEO, 3 giám đốc và 12 chuyên viên. Mỗi agent có bộ não, trí nhớ, kiến thức và kinh nghiệm riêng. Owner giao mục tiêu, giám sát và phê duyệt.

> **Trạng thái: thiết kế v0.2, đã cập nhật theo câu trả lời của Owner ngày 26/11/2026; chờ Owner ghi "duyệt kiến trúc".** Chưa có mã. Xem `docs/IMPLEMENTATION_PLAN.md` §7.
>
> Đã quyết:
> - chạy trên máy Windows 11 của Owner;
> - LangGraph;
> - Claude + ChatGPT;
> - Telegram là kênh của Owner;
> - AI tự xuất bản FAQ/blog (có 5 lớp chặn, gỡ được ngay);
> - trần LLM 50 USD.

| Tài liệu | Nội dung |
|---|---|
| [docs/SRS-v1.0.md](docs/SRS-v1.0.md) | Đặc tả gốc của Owner |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Kiến trúc, nguyên tắc, triển khai, 14 quyết định (ADR) có lý do, ưu, nhược, chi phí, mở rộng; chi phí vận hành; mở rộng 100 agent; rủi ro |
| [docs/BRAIN_SPEC.md](docs/BRAIN_SPEC.md) | **Agent Brain Blueprint**: bộ não riêng, 4 loại trí nhớ, truy hồi, phân quyền trí nhớ, Learning Engine, thang bằng chứng, đánh giá độc lập, phiên bản bộ não |
| [docs/AGENT_DESIGN.md](docs/AGENT_DESIGN.md) | 15 agent: nhiệm vụ, model, công cụ, KPI, luật cứng, mức khả dụng; giao tiếp; giải quyết bất đồng |
| [docs/DATABASE_SCHEMA.md](docs/DATABASE_SCHEMA.md) | Lược đồ PostgreSQL + pgvector, RLS, audit chuỗi băm |
| [docs/SECURITY_PLAN.md](docs/SECURITY_PLAN.md) | Mô hình đe dọa, quyền 4 cấp, phê duyệt, chống prompt injection, Content Gate, sao lưu |
| [docs/TEST_PLAN.md](docs/TEST_PLAN.md) | Kiểm thử theo tầng; ánh xạ đủ 25 tiêu chí nghiệm thu |
| [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md) | Lộ trình 10 Sprint, đề xuất công nghệ và phụ thuộc, kế hoạch chuyển từ dịch vụ AI hiện tại |
| [docs/DECISIONS.md](docs/DECISIONS.md) | **Sổ quyết định của Owner** và hệ quả kỹ thuật của từng quyết định |
| [docs/QUESTIONS_FOR_OWNER.md](docs/QUESTIONS_FOR_OWNER.md) | Câu hỏi cần Owner trả lời (§G: câu mới), mỗi câu có mặc định đề xuất |
| [CLAUDE.md](CLAUDE.md) | Quy tắc cho Claude Code khi phát triển |

Quan hệ với phần còn lại của repo:
- `../web` là website bán hàng, nguồn dữ liệu chính thức.
- `../ai` là dịch vụ AI cục bộ hiện tại, gồm bộ não "Trưởng văn phòng" (PR #5). Đây là thiết kế tham chiếu, chạy song song cho tới khi nền tảng này qua nghiệm thu.
