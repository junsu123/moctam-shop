# IMPLEMENTATION_PLAN: kế hoạch triển khai

> Trạng thái: **v0.2 đã duyệt** (26/11/2026 22:43). **Sprint 0, 1, 2, 3 xong** (báo cáo ở `progress/`); đang làm Sprint 4, chia 3 phần 4a/4b/4c, mỗi phần một PR (4a xong, `progress/sprint-4.md`). Owner ưu tiên trang quản trị trọn gói, nên Control Center có từ Sprint 1 và lớn dần theo từng Sprint (§3).

## 1. Tóm tắt cho Owner

- **Giữ nguyên** mọi chức năng SRS. Không lược bỏ mục nào.
- **Đã theo quyết định của Owner (v0.2):**
  - chạy trên máy Windows 11 cá nhân (ADR-01);
  - LangGraph (ADR-05);
  - Claude + ChatGPT (ADR-06);
  - Telegram là kênh của Owner (ADR-15);
  - AI tự xuất bản FAQ/blog có 5 lớp chặn (ADR-16);
  - trần LLM **50 USD/tháng** (phương án B);
  - máy RX 560 + 16 GB RAM: không LLM cục bộ, hệ thống gọn trong 6 GB;
  - lịch đăng bài theo giờ vàng, tăng dần 3 giai đoạn;
  - Owner tự cài đặt Telegram trong dashboard.
- **Vẫn đề xuất, chờ Owner duyệt:**
  1. Langfuse và n8n để giai đoạn sau (ADR-08, ADR-09).
  2. Đổi thứ tự Sprint: làm một **lát cắt dọc** chạy được đầu–cuối sớm (§2).
  3. Nền tảng không ghi thẳng vào CSDL website; mọi thao tác đi qua API có khóa phạm vi (P1). Ẩn danh dữ liệu khách đã được Owner đồng ý (Q-L1).
- **Kế thừa** bộ não "Trưởng văn phòng" đang chạy (PR #5) làm thiết kế tham chiếu. Dịch vụ AI cũ vẫn chạy cho tới khi nền tảng mới qua nghiệm thu.
- **Rủi ro lớn nhất** không nằm ở mã, mà ở: chi phí LLM, và quyền truy cập API của từng nền tảng (TikTok, Shopee, Meta, Zalo). Owner đã chọn bỏ qua phần pháp lý.

## 2. Vì sao đổi thứ tự Sprint

**Bổ sung khi duyệt (22:43):** Owner ưu tiên trang quản trị trọn gói. Control Center không còn dồn vào Sprint 8. Sprint 1 đã có trang dùng được; mỗi Sprint sau thêm màn hình cho phần vừa xong. Owner điều hành được hệ thống ngay từ khi agent đầu tiên chạy.


Lộ trình SRS §20 xây theo **lớp ngang**: nền tảng → lõi agent → trí nhớ → điều phối → học → agent → dashboard. Rủi ro của cách này là tới Sprint 8 mới thấy cả hệ thống chạy cùng nhau, nên lỗi tích hợp lộ ra muộn và đắt.

Đề xuất: giữ đủ nội dung các Sprint của SRS, nhưng **ở Sprint 4 dựng một lát cắt dọc**:

> Owner → AI CEO → Marketing Director → SEO Agent + Content Agent → **tự xuất bản** lên website moctam **thật** (qua 5 lớp chặn) → link về Telegram → Owner gỡ hoặc góp ý → học từ phản hồi → AC-BRAIN-01 đạt cho 2 agent.

Từ đó các Sprint sau chỉ là *mở rộng theo chiều ngang* trên khung đã chứng minh.

## 3. Lộ trình

Kích thước tương đối: S ≈ 1 tuần, M ≈ 2 tuần, L ≈ 3 tuần (một lập trình viên + Claude Code). Con số chỉ để so sánh. Thời gian thực phụ thuộc nguồn lực và phản hồi của Owner.

| Sprint | Nội dung (giữ đủ mục SRS §20) | Kích thước | Tiêu chí thoát (đo được) | Cần Owner trước |
|---|---|---|---|---|
| **0. Quyết định và khung** | Owner duyệt thiết kế; CI (lint, type, test, quét secret); `CLAUDE.md`; mẫu PR có DoD; **hướng dẫn cài đặt trên Windows 11** (Docker Desktop/WSL2, `.wslconfig` giới hạn 6 GB, tự khởi động, tắt chế độ ngủ, BitLocker, sao lưu) | S | CI xanh trên khung rỗng; `docker compose up` chạy được trên máy Owner (16 GB RAM) | **Duyệt kiến trúc** |
| **1. Foundation + Control Center v1** | Backend FastAPI, **trang quản trị dùng được**: đăng nhập + 2FA, Tổng quan, Cài đặt (Telegram, ngân sách LLM, giờ làm việc), danh sách agent (đọc từ registry, nút tạm dừng/chạy lại ghi audit), khung màn hình Diễn biến (SSE); i18n vi, Postgres + pgvector, Redis/Valkey, Docker Compose, Authentication + 2FA Owner, **Model Gateway** (adapter **Anthropic + OpenAI**, registry có giá thật, chi phí, trần ngày/tháng, che dữ liệu), log + OpenTelemetry, audit chuỗi băm, **Telegram Gateway bản thông báo** + **trang Cài đặt → Telegram** (dán token, kết nối bằng mã 6 số, loại tin, giờ yên lặng) | L | UT-MGW-* đạt; gọi thật Claude và OpenAI qua gateway; IT-DB-01/03, IT-TG-01…05 đạt; Owner tự cài bot và nhận tin Telegram đầu tiên | — |
| **2. Agent Core** | Agent Registry, vòng đời, Brain Loader (bundle YAML, schema, hash, phiên bản, ghim), cấu hình agent, **Tool Registry + Tool Gateway**, **Policy Engine** (4 cấp, danh sách bắt buộc duyệt, hạn mức), `approvals` Control Center: **trang từng agent** (danh tính, bộ não đang chạy, quyền công cụ, lịch sử phiên bản) + **hàng chờ phê duyệt**. | L | UT-AG-*, UT-BRAIN-*, UT-POL-*, UT-TOOL-* đạt; tạm dừng/tiếp tục agent qua API | — |
| **3. Memory System** | Private/dept/shared, episodic/semantic/procedural/working, RLS, truy hồi lai + chuẩn hóa tiếng Việt, embedding qua gateway (cục bộ/đám mây), `memory_access_log` Control Center: **xem trí nhớ** của agent (lọc theo loại, phạm vi, nguồn). | M | UT-MEM-*, IT-DB-02, IT-VEC-*, PT-03 đạt | Q-T3 (GPU) |
| **4. Orchestration + lát cắt dọc** | **Đồ thị LangGraph** (checkpoint Postgres, `interrupt` + tiếp tục qua Telegram, job đối soát), AI CEO, 3 Director, Task Engine (9 trạng thái, lease, retry, phụ thuộc), Message Bus (outbox), cộng tác + giải quyết bất đồng; **SEO + Content Agent** chạy đầu–cuối với website moctam thật; **website thêm API `publish`/`unpublish` + sửa AT-09** (trong `web/`); **Content Gate**; **tự xuất bản theo lịch giờ vàng 3 giai đoạn** (hàng chờ xuất bản, chạy lại Content Gate trước giờ đăng, tự lùi giai đoạn) **+ link Telegram + nút Gỡ bài**; trang *Cài đặt → Lịch đăng bài*; **màn hình "Diễn biến trực tiếp" bản đầu** (dựa trên bản mẫu ở `ai/`, đọc `tasks`, `task_logs`, checkpoint LangGraph, `agent_messages`, SSE); Evaluation Service bản đầu (tất định + phản hồi người + OpenAI chấm chéo); **Claude soạn bản giọng văn thương hiệu** để Owner duyệt | L+ | IT-ORCH-01/02, IT-REC-*, IT-A2A-*, IT-LG-*, IT-PUB-01…07, WEB-AT-09' đạt; **AC-BRAIN-01 đạt cho SEO và Content**; số liệu chi phí thật cho 1 tuần chạy thử | Q-B2 |
| **5. Learning Engine** | Research Collector, Knowledge Extractor (đọc cách ly), Validator (5 cửa), Memory Manager (gộp/tóm tắt), Experience Evaluator (thang bằng chứng), Learning Scheduler, Knowledge Version Manager, shadow brain Control Center: **Trung tâm học tập** (kiến thức mới, đề xuất cải thiện, duyệt kiến thức). | L | LT-01…08 đạt; một bài học L2 sinh ra từ dữ liệu thật có nhãn "tương quan" | — |
| **6. Chuyên viên đợt 1** | SEO và Content (hoàn thiện), Social, Creative (+ **Claude thiết kế brand guidelines hình ảnh**: màu, font, logo, mẫu ảnh, dựa trên giao diện website hiện tại, Owner duyệt), Data Analyst (sandbox tính toán, schema phân tích) | L | AC-BRAIN-01 đạt cho 5 agent; ST-01…06 đạt với các agent đọc web; brand guidelines đã duyệt nằm trong shared knowledge | Q-I1, Q-I6 |
| **7. Chuyên viên đợt 2** | Ads, Customer, Affiliate, Sales Intelligence, Web CRO, Automation | L | AC-BRAIN-01 đạt cho 15 agent; Content Gate chặn đúng bộ câu cấm; mỗi lead có `source_url` | Q-I2…I5 |
| **8. Hoàn thiện Control Center + tích hợp** | Phần còn lại của SRS §12: quản lý bộ não (so sánh, rollback), Task Center (Kanban + bảng), chat agent, chat công ty, phân tích kinh doanh; Integration Layer theo thứ tự Q-O4: **GSC + GA4** → website (bổ sung endpoint) → Facebook/TikTok → Shopee/TikTok Shop, CRM, email, Zalo → quảng cáo, **tùy theo điều kiện API thực tế** | L+ | E2E-01…12 đạt; mỗi tích hợp đã bật có IT-INT riêng; tích hợp chưa đủ điều kiện hiện "chưa kết nối" | Q-I* |
| **9. Test và production** | Security test đầy đủ, performance, backup/DR (IT-WIN-*), giám sát, chạy chính thức trên máy Windows của Owner, chuyển dần từ dịch vụ AI cũ | M | Toàn bộ AC-01…25 đạt; IT-BK-01 trên production; báo cáo nghiệm thu | — |

## 4. Chuyển từ dịch vụ AI hiện tại (`ai/`)

1. Sprint 4–7: hai hệ thống chạy song song. Nền tảng mới dùng tiền tố `client_ref` riêng (`co:`), tránh trùng bản nháp.
2. Mỗi tác nhân cũ (FAQ, blog, mua kèm, chăm sóc) chỉ tắt khi agent mới tương ứng đạt AC-BRAIN-01 **và** có tỉ lệ duyệt trong 2 tuần ≥ tỉ lệ duyệt của tác nhân cũ.
3. Kinh nghiệm đã học ở dịch vụ cũ (`brain_feedback`, ghi chú góp ý, độ tin cậy) được nhập vào experience/procedural memory của agent mới tương ứng (script một lần, có test).

## 5. Công nghệ và phụ thuộc đề xuất (bước 4)

Phiên bản cụ thể được khóa ở Sprint 0. Giấy phép cần kiểm tra lại ở thời điểm khóa.

| Thành phần | Đề xuất | Giấy phép (cần kiểm tra lại) | Phương án khác |
|---|---|---|---|
| Ngôn ngữ backend | Python 3.12, quản lý gói `uv` | PSF / MIT-Apache | Poetry |
| Web framework | FastAPI + Uvicorn | MIT / BSD | Litestar |
| ORM, migration | SQLAlchemy 2 (async) + Alembic | MIT | SQLModel |
| Validate | Pydantic v2 | MIT | — |
| Driver Postgres | psycopg 3 | LGPL-3.0 (dùng như thư viện, không đổi mã) | asyncpg (Apache-2.0) |
| CSDL | PostgreSQL 16/17 + pgvector + pg_trgm + unaccent | PostgreSQL License | — |
| Hàng đợi | Dramatiq + Redis | LGPL-3.0 | Celery (BSD) |
| Điều phối (v0.2) | **LangGraph** + `langgraph-checkpoint-postgres` | MIT | — |
| SDK LLM (v0.2) | `anthropic`, `openai` (bọc trong Model Gateway) | MIT / Apache-2.0 | — |
| Telegram (v0.2) | httpx gọi thẳng Bot API (đổi ở Sprint 1, xem DECISIONS) | BSD-3 | aiogram (MIT), python-telegram-bot (LGPL-3.0) |
| Chạy trên Windows (v0.2) | Docker Desktop (backend WSL2) | Điều khoản Docker: miễn phí cho doanh nghiệp nhỏ (cần kiểm tra) | Docker Engine cài trong WSL2 Ubuntu |
| Redis | Valkey hoặc Redis | Valkey BSD-3; Redis bản mới có thay đổi giấy phép, **cần chọn** | — |
| HTTP client | httpx | BSD-3 | aiohttp |
| Log, trace | structlog + OpenTelemetry SDK | MIT/Apache-2.0 | — |
| Mật mã | `cryptography` (AES-GCM), `argon2-cffi`, `pyotp` | Apache/BSD, MIT, MIT | — |
| Tool chuẩn hóa | MCP Python SDK (cho công cụ ngoài) | MIT | — |
| LLM cục bộ | Ollama (đơn giản) hoặc vLLM (thông lượng cao) | MIT / Apache-2.0 | llama.cpp server |
| Frontend | Next.js + TypeScript + Tailwind CSS + thư viện component headless; TanStack Query; next-intl | MIT | — |
| Test | pytest, pytest-asyncio, hypothesis, testcontainers, Playwright, Vitest, Locust | MIT/Apache/MPL | k6 |
| Bảo mật CI | gitleaks, pip-audit, bandit, semgrep, Trivy | MIT/Apache/LGPL | — |
| Xem dashboard từ xa (tùy chọn) | Tailscale | BSD-3 (client) | Cloudflare Tunnel |
| Tùy chọn giai đoạn sau | Langfuse, n8n | MIT (core) / Sustainable Use License | — |

## 6. Báo cáo tiến độ (bước 9)

- Cuối mỗi Sprint có `docs/progress/sprint-N.md`, gồm: việc đã xong (kèm số test đạt), việc chưa xong và lý do, chi phí LLM thực tế so với dự toán, rủi ro mới, câu hỏi mới cho Owner.
- Bảng **chức năng còn thiếu so với SRS** được cập nhật liên tục trong `docs/progress/SRS-COVERAGE.md`: mỗi mục SRS có trạng thái `chưa làm / đang làm / xong (test X)`.

## 7. Việc Owner cần làm ngay

1. Xem `DECISIONS.md`: kiểm tra mình đã hiểu đúng câu trả lời của Owner chưa.
2. ~~Trả lời 4 câu 🔴 mới~~: đã trả lời đủ (lần 3, 21:53).
3. ~~Ghi "duyệt kiến trúc"~~: đã duyệt 26/11/2026 22:43. Sprint 0 đang làm; tiến độ ở `docs/progress/`.
