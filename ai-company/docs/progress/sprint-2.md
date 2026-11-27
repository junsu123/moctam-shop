# Báo cáo Sprint 2: Agent Core

Thời gian: 27/11/2026. Owner duyệt "Sprint 2" sau khi gộp PR #8, #9.

Sprint này cho mỗi agent một **bộ não riêng có phiên bản**, và đặt mọi hành động của agent sau hai lớp kiểm soát:
- **Policy Engine**: cho phép, cần duyệt hay chặn;
- **Tool Gateway**: chạy có kiểm soát, không làm hai lần.

Control Center có thêm trang từng agent, hàng chờ phê duyệt và danh mục công cụ.

## Đã xong (kèm bằng chứng)

**Bộ não (`brains/`)**
- Hiến pháp chung `_core/constitution.yaml`:
  - nguyên tắc;
  - hành động bị cấm ở mọi cấp: đổi giá, thanh toán, đọc secret, sửa mã, tự cấp quyền;
  - danh sách luôn cần người duyệt (10 loại);
  - nhóm rủi ro cao;
  - hạn duyệt 72 giờ.
- 5 mẫu phòng ban: Điều hành, Giám đốc, Chuyên viên Marketing/Kinh doanh/Công nghệ.
- 15 thư mục agent, soạn theo AGENT_DESIGN §4:
  - danh tính, sứ mệnh, nhiệm vụ;
  - luật cứng;
  - tính cách (tham số số);
  - kỹ năng;
  - quyền công cụ (cấp 1–4, hạn mức, cờ luôn duyệt);
  - KPI.

**Brain Loader (`app/brain/`)**
- Ghép mẫu (`extends`).
- Kiểm schema chặt: gõ sai tên trường cũng là lỗi. Lỗi nêu đúng đường dẫn trường bằng tiếng Việt, ví dụ `identity.role.mission: thiếu trường bắt buộc`.
- Đối chiếu quyền với Tool Registry và hiến pháp, ví dụ "cấp L2 thấp hơn cấp tối thiểu L3".
- Hai mã kiểm tra: `bundle_hash` và `core_rules_hash` (hiến pháp + luật cứng + quyền).

**Registry bộ não**
- Nạp lần đầu: tự ghim hash cốt lõi, vì bundle trong git đã qua review PR.
- Có nội dung mới:
  - bắt buộc tăng `brain_version`;
  - tạo bản nháp kèm danh sách khác biệt;
  - tạo yêu cầu "thăng hạng bộ não" rủi ro cao.
- Owner duyệt thì bản mới chạy, quyền công cụ đổi theo, hash cốt lõi được ghim.
- Runtime:
  - nạp đúng phiên bản ghim theo task;
  - kiểm lại hash;
  - hash cốt lõi chưa được duyệt thì từ chối nạp.
- Bản chạy thử (shadow) không được giao kết quả.
- Quay lại phiên bản cũ bằng một thao tác.
- Changelog `agent_versions` chỉ thêm: trigger chặn sửa và xóa.

**Tham số tính cách đi vào mã (`behavior.py`)**
- `evidence_strictness`: chặn kết quả thiếu nguồn.
- `risk_tolerance`: dời ngưỡng tự tin để hỏi cấp trên.
- `verbosity`: giới hạn độ dài báo cáo.
- Test chứng minh cùng một đầu vào cho ra quyết định khác nhau giữa hai agent.

**Vòng đời agent**: bảng chuyển trạng thái hợp lệ. Ví dụ: agent đang tắt phải qua "tạm dừng" rồi mới chạy lại được. Tạm dừng, tiếp tục và tạm dừng tất cả đều đi qua bảng này.

**Policy Engine (`app/policy/engine.py`)**
- Thứ tự quyết định:
  1. mặc định từ chối;
  2. trạng thái agent;
  3. bộ não nạp được;
  4. hiến pháp cấm;
  5. quyền và hạn quyền;
  6. cấp tự chủ;
  7. hạn mức: lần/ngày, USD/lần, ngân sách AI/ngày của agent;
  8. **danh sách bắt buộc duyệt, kể cả ở L4**;
  9. quyền có cờ luôn duyệt;
  10. taint với hành động ra ngoài.
- Mọi quyết định ghi vào `policy_decisions` kèm lý do.

**Tool Gateway (`app/tools/`)**
- Danh mục 30 công cụ theo AGENT_DESIGN.
  - Có 2 công cụ chạy thật không cần tích hợp: `signals.read` và `notify.owner` (báo cáo cho Owner qua Telegram).
  - Các công cụ còn lại trả `NOT_CONFIGURED` cho tới khi có tích hợp.
- Mỗi lời gọi:
  - kiểm schema đầu vào và đầu ra;
  - timeout, thử lại theo chính sách (chỉ lỗi tạm thời);
  - khóa chống trùng: tác động và việc đánh dấu thành công nằm chung một giao dịch, gọi lại cùng khóa chỉ trả kết quả cũ;
  - phê duyệt gắn digest của nội dung: nội dung đổi thì phải duyệt lại;
  - ghi `tool_invocations` và audit.

**Hàng chờ phê duyệt**
- Hạn 72 giờ. Hết hạn tự hủy: im lặng không phải đồng ý.
- Rủi ro cao chỉ duyệt được sau khi xác thực lại.
- Mỗi yêu cầu báo qua Telegram.

**API**
- `GET /agents/{key}`: danh tính, bộ não đang chạy, độ toàn vẹn, quyền, chi phí hôm nay.
- Bộ não: `/agents/{key}/brains`, `…/brains/diff`, `…/shadow`, `…/rollback` (cần xác thực lại).
- `/agents/{key}/history`, `POST /brains/sync`, `/tools`.
- Phê duyệt: `/approvals`, `/approvals/count`, `/approvals/{id}/decide`.

**Việc hoãn từ Sprint 1**
- **OpenTelemetry**:
  - span cho request, `tool.invoke`, `policy.authorize`, `llm.complete`, httpx;
  - `trace_id`/`span_id` có trong log JSON;
  - gửi OTLP khi đặt `AICO_OTEL_ENDPOINT`;
  - RAM backend tăng khoảng 15 MB, vẫn trong giới hạn 768 MB.
- **Chống dùng lại mã TOTP**: mỗi bước 30 giây chỉ dùng được một lần.

**Control Center**
- Trang `/agent/[key]` có 4 tab:
  - Hồ sơ: sứ mệnh, luật cứng, tính cách, tổ chức, model và giới hạn, kỹ năng, KPI;
  - Bộ não: bản đang chạy, độ toàn vẹn, các phiên bản, so sánh, chạy thử, quay lại, đọc lại thư mục;
  - Quyền công cụ;
  - Lịch sử: changelog, quyết định chính sách, lời gọi công cụ.
- Trang `/phe-duyet`: tab Đang chờ và Đã xử lý. Có bảng khác biệt hoặc nội dung agent muốn gửi. Từ chối kèm góp ý. Việc rủi ro cao hiện hộp xác thực lại.
- Thanh bên có mục "Phê duyệt" kèm số việc đang chờ. Tổng quan báo việc chờ duyệt.
- Cài đặt có thêm tab **Công cụ**.

**Vận hành**
- `python -m app.cli sync-brains`.
- Compose: dịch vụ `migrate` nạp bộ não sau khi cập nhật lược đồ; thư mục `brains/` được gắn chỉ đọc.

**Kiểm chứng**

| Bộ test | Số test đạt |
|---|---|
| `test_brain.py`: UT-AG-01…05, UT-BRAIN-01…08 | 16 |
| `test_policy.py`: UT-POL-01…12 | 15 |
| `test_tools.py`: UT-TOOL-01…06 | 7 |
| `test_api_agent_core.py`: API, OpenTelemetry, chống dùng lại mã | 9 |

- Tổng **112 test backend đạt**; ruff, ruff format, mypy strict đều sạch.
- Frontend: tsc, eslint, build đạt.
- **E2E 1/1 đạt**, đi hết luồng: thêm trang agent (4 tab), agent xin duyệt thật qua Tool Gateway, Owner từ chối kèm góp ý, tab Công cụ. Có 17 ảnh chụp.

## Lệch so với kế hoạch (ghi trung thực)

| Kế hoạch | Thực tế | Lý do / xử lý |
|---|---|---|
| Bảng `agent_profiles`, `agent_skills` (DATABASE_SCHEMA) | Chưa tạo. Danh tính và kỹ năng đọc từ bộ não đang chạy | Tránh hai nguồn sự thật. `agent_skills` gắn với procedural memory ở Sprint 3/5 |
| Sửa quyền agent trên dashboard | Quyền chỉ đến từ `tools/tool_permissions.yaml`; dashboard chỉ xem | Đổi quyền là đổi bộ não, nên phải qua duyệt "thăng hạng" (rủi ro cao). Không có đường nào khác để ghi quyền |
| Nạp bộ não lần đầu cần Owner duyệt? | Lần đầu tự ghim hash (bootstrap) | Bundle trong git đã qua review PR. Mọi thay đổi sau đó đều cần Owner duyệt |
| Nút Duyệt/Từ chối trên Telegram | Telegram chỉ báo có việc chờ duyệt | Nút ký HMAC làm cùng LangGraph `interrupt` ở Sprint 4 (IT-TG-02/03) |
| Ngân sách AI theo agent trong Model Gateway | Policy Engine đã kiểm ngân sách AI/ngày của agent khi lời gọi công cụ có ước tính chi phí; Model Gateway mới kiểm trần chung | Gắn trần theo agent vào Model Gateway khi runtime gọi model thay agent (Sprint 4) |

## Việc chuyển sang Sprint sau (đã ghi, chưa làm)

- Sprint 3, Memory System: trí nhớ 4 loại, RLS, truy hồi lai tiếng Việt, xem trí nhớ trên dashboard.
- Sprint 4:
  - runtime LangGraph dùng `registry.resolve` (bộ não ghim theo task) và `gateway.invoke`;
  - nút duyệt trên Telegram;
  - Content Gate gắn `publish_risky`;
  - trần AI theo agent trong Model Gateway.
- Còn từ Sprint 0/1: kiểm thử `docker compose up` trong CI; chạy `khoi-dong.ps1` thật trên Windows.

## Owner làm gì để dùng

1. Tải mã mới, chạy `scripts\windows\khoi-dong.ps1`. Dịch vụ `migrate` tự nạp bộ não cho 15 agent.
2. Vào **Agent**, bấm tên một agent để xem hồ sơ, bộ não và quyền.
3. Khi có việc cần duyệt, thanh bên hiện số và Telegram báo tin. Vào **Phê duyệt** để duyệt hoặc từ chối kèm góp ý.

## Chi phí LLM trong Sprint

0 USD. Test dùng nhà cung cấp giả; chưa có agent nào gọi model thật.
