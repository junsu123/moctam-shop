# Báo cáo Sprint 4: Orchestration + lát cắt dọc

Sprint 4 lớn nhất kế hoạch (L+), chia làm 3 phần, mỗi phần một PR để Owner duyệt dần:

| Phần | Nội dung | Trạng thái |
|---|---|---|
| **4a** | Task Engine, Message Bus, đồ thị nhận thức LangGraph, worker, đối soát, lịch tự động, trang Việc, văn phòng trực tiếp | **xong** (PR #12) |
| 4b | Website thêm API xuất bản/gỡ bài, Content Gate, hàng chờ + lịch đăng 3 giai đoạn, nút Telegram có chữ ký | chưa làm |
| 4c | Lát cắt dọc Owner → CEO → Marketing Director → SEO + Content → xuất bản → học từ phản hồi; giải quyết bất đồng; Evaluation; AC-BRAIN-01 | chưa làm |

Báo cáo này được bổ sung sau mỗi phần; phần tổng kết Sprint viết khi xong 4c.

## Phần 4a: bộ máy chạy việc (27–28/11/2026)

Sau phần này, agent **làm việc thật** theo đồ thị nhận thức.

Owner (hoặc agent cấp trên, hoặc lịch tự động) giao việc. Agent tự đi qua các bước:
1. nhớ lại kinh nghiệm;
2. lập kế hoạch;
3. kiểm quyền từng bước;
4. dùng công cụ được phép hoặc giao tiếp việc;
5. tự kiểm tra;
6. nộp review hoặc xin duyệt;
7. ghi trải nghiệm vào trí nhớ riêng.

Mọi bước hiện trực tiếp trên dashboard. Tắt máy giữa chừng thì chạy tiếp đúng chỗ, không làm lại việc đã làm.

### Đã xong (kèm bằng chứng)

**Task Engine (`app/tasks/engine.py`, migration `0005_tasks`)**
- 9 trạng thái của SRS. Chuyển trạng thái được kiểm trong mã và bằng trigger của CSDL; ghi sai thì CSDL từ chối (UT-TASK-01).
- Phụ thuộc giữa các việc, phát hiện vòng lặp (UT-TASK-02).
- Hợp đồng giao việc giữa agent (UT-TASK-03):
  - bắt buộc có tiêu chí thành công đo được, ngân sách, hạn chót;
  - ngân sách việc con ≤ phần còn lại của việc cha; hạn chót và cấp tự chủ không vượt việc cha;
  - cây việc sâu tối đa 4 tầng, mỗi việc tối đa 6 việc con;
  - chống vòng lặp: cùng người giao, người nhận, loại việc quá 3 lần/giờ thì chặn.
- Nhận việc bằng lease (UT-TASK-04):
  - ưu tiên việc khẩn;
  - mỗi agent một việc một lúc;
  - agent tạm dừng không nhận việc;
  - worker chết thì lease hết hạn và worker khác nhận lại.
- Thử lại có giãn cách (30 s, 60 s, …) với lỗi tạm thời. Hết lượt thì báo lỗi cho cấp trên qua message `error_report` (UT-TASK-05).
- Hủy việc lan xuống mọi việc con; yêu cầu duyệt đang chờ của chúng cũng bị hủy (UT-TASK-06).

**Message Bus (`app/tasks/bus.py`)**
- Có đủ 8 loại message của SRS §6.1.
- Bảng `agent_messages` đồng thời là outbox:
  - ghi cùng giao dịch với thay đổi gây ra nó;
  - giao ít nhất một lần, có thử lại;
  - nhận trùng thì bỏ qua (IT-A2A-01).
- Message sai hợp đồng không thử mãi, và việc cha không bị chờ mãi.
- `knowledge_sharing` chỉ vào hộp ứng viên, không ghi thẳng vào trí nhớ của ai (IT-A2A-04).

**Đồ thị nhận thức (`app/tasks/runtime.py`, `app/tasks/graph.py`)**
- Thứ tự các nút: đọc việc → nhớ lại → lập kế hoạch → kiểm quyền → làm từng bước → chờ việc đã giao → soạn kết quả → tự kiểm tra → review/duyệt → ghi trải nghiệm.
- Mỗi việc chạy theo bộ não được ghim lúc tạo. Model được gọi theo hồ sơ của bộ não qua Model Gateway; chi phí cộng vào việc ngay khi gọi.
- Policy Engine chặn một bước → agent lập lại kế hoạch (tối đa 2 lần) → vẫn bị chặn thì báo lỗi; bước bị chặn không chạy.
- Tự kiểm tra là kiểm tra **tất định**, không tự chấm điểm. Có các loại tiêu chí:
  - đủ trường, độ dài;
  - phải có hoặc không được có cụm từ;
  - giá trị hợp lệ;
  - số mục;
  - kiểm tra kèm theo góp ý cũ trong trí nhớ.
- Chưa đạt thì làm lại kèm danh sách vấn đề (IT-LG-01).
- Giao việc cho agent khác:
  - việc con được tạo qua Message Bus;
  - việc cha dừng chờ, xong thì chạy tiếp với kết quả của việc con;
  - việc con được người giao review: cấp trên nhận một việc "Review" riêng. Kết luận "sửa lại" kèm góp ý và kiểm tra thì việc con làm lại theo góp ý;
  - góp ý thành "Bài học" trong trí nhớ riêng của agent (IT-A2A-02).
- Checkpoint lưu trong Postgres sau từng nút:
  - worker bị giết giữa chừng thì worker khác chạy tiếp từ nút dở;
  - công cụ đã chạy không chạy lại (IT-REC-01);
  - đang chờ duyệt mà khởi động lại cả hệ thống thì vẫn chờ, duyệt xong mới chạy tiếp (IT-REC-02).
- Owner từ chối kèm góp ý thì việc bị hủy, và góp ý thành trải nghiệm của agent.

**Worker, đối soát, lịch**
- Dịch vụ `worker` (`python -m app.workers.agents`) chạy tối đa 3 việc song song. RAM đo được khoảng 135 MB khi rảnh; giới hạn trong compose là 384 MB.
- Đối soát chạy mỗi 5 phút (IT-LG-03):
  - nhận lại việc mất worker;
  - chuyển lỗi việc quá giờ;
  - hủy việc có yêu cầu duyệt hết hạn (im lặng không phải là đồng ý);
  - báo checkpoint mồ côi; dọn checkpoint cũ hơn 30 ngày;
  - báo việc quá hạn chót.
- Lịch tự động bằng cron 5 trường theo giờ Việt Nam. Máy tắt rồi bật lại trong vòng 24 giờ thì chạy bù **một** lần, không dồn (IT-REC-03).

**API và Control Center**
- API mới:
  - `/tasks`: danh sách, thống kê, chi tiết từng bước, giao việc, hủy, chạy lại, Owner review;
  - `/tasks/{id}/state`: chẩn đoán checkpoint;
  - `/live`;
  - `/schedules`.
- Trang **Việc** (thanh bên) có 4 tab: Đang chạy, Chờ duyệt/review, Xong, Lỗi/đã hủy. Có hộp "Giao việc" để chọn agent, việc, thế nào là xong, ngân sách, hạn chót, có cần review hay duyệt không.
- Trang một việc:
  - tóm tắt trạng thái, chi phí, hạn chót, lượt thử;
  - khung **review của Owner**: duyệt, yêu cầu sửa (bắt buộc ghi góp ý), từ chối;
  - 4 tab: Từng bước, Kết quả, Việc con/review, Trao đổi/công cụ.
- **Diễn biến** có thêm tab "Bước của agent" (mọi bước của mọi việc, trực tiếp) và tab **Văn phòng**:
  - mỗi agent một bàn làm việc: đang làm việc gì, ở bước nào, bao nhiêu việc chờ, xong bao nhiêu trong 24 giờ;
  - trên cùng là những gì đang chờ anh/chị.
- Trang agent có thêm tab **Việc**.

### Kiểm chứng

| Bộ test | Đạt |
|---|---|
| `test_tasks.py`: UT-TASK-01…07, IT-REC-03, IT-A2A-01, IT-A2A-04 | 11 |
| `test_runtime.py`: IT-LG-01, IT-REC-01, IT-REC-02 (duyệt và từ chối), Policy chặn → lập lại kế hoạch, IT-A2A-02 (giao việc → review → sửa → duyệt → việc cha chạy tiếp), IT-LG-03 | 7 |
| `test_api_tasks.py`: Owner giao việc, review hai vòng, hủy/chạy lại, văn phòng, lịch | 3 |

- Toàn bộ backend: **151 test đạt**. ruff, ruff format, mypy strict đều sạch. Frontend: tsc, eslint, build đạt.
- **E2E đạt.** E2E chạy thêm một "nhà cung cấp AI giả" (chỉ trong `e2e/`) để agent chạy thật mà không tốn tiền. Luồng thêm:
  1. Owner giao việc cho Chăm sóc khách, có review;
  2. agent làm qua đủ đồ thị;
  3. Owner yêu cầu sửa "nói rõ giờ chốt đơn là 15 giờ";
  4. agent sửa đúng theo góp ý;
  5. Owner duyệt, việc xong;
  6. Văn phòng hiện "1 xong trong 24 giờ"; trí nhớ của agent có "Bài học".

### Lệch so với kế hoạch (ghi trung thực)

| Kế hoạch | Thực tế | Lý do |
|---|---|---|
| Dramatiq làm hàng đợi đánh thức (ADR-04) | Bảng `tasks` + lease là hàng đợi; Redis chỉ đánh thức | Ít thành phần và RAM hơn, trạng thái chỉ ở một nơi. ADR-04 đã ghi cập nhật |
| `task_assignments`, `task_outputs`, `task_messages` | Chưa tạo | Lịch sử nằm trong `task_logs`, message có `task_id`, bản nháp trong `output_data`. Tạo khi cần |
| Chuyển trạng thái của SRS | Thêm IN_PROGRESS → PENDING (chờ việc con) và ASSIGNED → PENDING | Việc cha chờ việc con không giữ worker. DATABASE_SCHEMA đã sửa |
| Working memory trên Redis cho từng task | Trạng thái làm việc nằm trong checkpoint LangGraph | Một nguồn sự thật, sống qua khởi động lại. Lớp Redis từ Sprint 3 vẫn còn cho việc cần chia sẻ nhanh |

### Việc còn lại của Sprint 4

- 4b: xuất bản lên website thật, Content Gate, lịch đăng 3 giai đoạn, nút Telegram (IT-PUB-01…07, IT-LG-02, WEB-AT-09').
- 4c:
  - CEO → Director → SEO + Content trên dữ liệu thật;
  - giải quyết bất đồng (IT-A2A-03);
  - Evaluation bản đầu;
  - bản giọng văn thương hiệu để Owner duyệt;
  - IT-ORCH-01/02, AC-BRAIN-01.
- Số liệu chi phí 1 tuần chạy thử: cần Owner chạy trên máy với khóa API thật, sau 4c.
