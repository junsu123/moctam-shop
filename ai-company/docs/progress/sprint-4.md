# Báo cáo Sprint 4: Orchestration + lát cắt dọc

Sprint 4 lớn nhất kế hoạch (L+), chia làm 3 phần, mỗi phần một PR để Owner duyệt dần:

| Phần | Nội dung | Trạng thái |
|---|---|---|
| **4a** | Task Engine, Message Bus, đồ thị nhận thức LangGraph, worker, đối soát, lịch tự động, trang Việc, văn phòng trực tiếp | **xong** (PR #12) |
| **4b** | Website thêm API xuất bản/gỡ bài, Content Gate, hàng chờ + lịch đăng 3 giai đoạn, nút Telegram có chữ ký, trang Xuất bản | **xong** (PR #13) |
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

## Phần 4b: tự xuất bản FAQ/blog (28/11/2026)

Sau phần này, agent viết FAQ/blog **đăng thẳng lên website**, theo đúng 5 lớp chặn của ADR-16. Anh/chị nhận link qua Telegram và gỡ được bằng một nút.

Đường đi của một bài:
1. Owner (hoặc cấp trên) giao việc "Viết FAQ/blog và đăng lên website".
2. Agent viết, tự kiểm tra (bài FAQ/blog tự có tiêu chí "có tiêu đề và nội dung").
3. **Giám đốc Marketing review** (lớp 2). Chưa đạt thì agent sửa theo góp ý.
4. Review đạt → nút `publish` của đồ thị gọi `site.publish`.
5. **Content Gate** (lớp 1) chạy *trước* Policy Engine:
   - cụm rủi ro, so sánh đối thủ, giá không khớp website, SĐT/email, mã HTML lạ → **chặn**, gửi thành bản nháp chờ nhân viên duyệt và báo Telegram;
   - chủ đề sức khỏe, dị ứng, giá, khuyến mãi, hoặc bộ phân loại (model rẻ) thấy rủi ro vừa/cao → **Owner duyệt** (lớp 3) bằng nút Duyệt/Từ chối trên Telegram hoặc dashboard. Không trả lời trong 72 giờ thì việc bị hủy.
6. Bài vào **hàng chờ**, được xếp vào khung giờ kế tiếp của lịch đăng (lớp 4).
7. Đến giờ: Content Gate chạy lại với dữ liệu website mới nhất → gọi website.
8. **Website kiểm lần cuối** (lớp 5): khóa `content:publish`, hạn mức ngày, giờ đăng, `info_version`, bộ lọc HTML.
9. Telegram gửi link kèm nút **Gỡ bài** và **Góp ý**.

### Đã xong (kèm bằng chứng)

**Website (`web/`)**
- Migration `010_ai_publish.sql`:
  - cột `contents.published_by` (`staff`/`ai`);
  - bảng `ai_publications`: mỗi lần AI đăng/gỡ, khóa chống trùng `client_ref` theo từng khóa API;
  - cài đặt `ai_publish_enabled`, hạn mức ngày FAQ 3 / blog 1, giờ đăng `07:00-21:30`.
- `POST /api/sync/publish` và `POST /api/sync/unpublish` (`app/src/Domain/AiPublisher.php`), phạm vi `content:publish`:
  - mã lỗi: `AI_PUBLISH_DISABLED` 423, `AI_PUBLISH_HOURS` 409, `AI_PUBLISH_QUOTA` 429 (đếm theo ngày giờ Việt Nam, có khóa dòng nên gửi song song cũng không vượt), `SOURCE_OUTDATED` 409;
  - chỉ gỡ được bài AI đăng; bài nhân viên đăng → `FORBIDDEN`;
  - đăng/gỡ đều ghi audit và báo về `/feedback` (`approved`/`retracted`) để agent học.
- Trang Khóa API có thêm phạm vi `content:publish`.
- Ca nghiệm thu **AT-09'** trong `web/tests/acceptance.php`. Toàn bộ **27/27 ca đạt**.
- `web/tests/it_server.sh` dựng website thật (PHP + MariaDB, CSDL tên chứa `test`) cho kiểm thử tích hợp; CI dùng script này.

**Content Gate (`app/content/gate.py`)**
- Kiểm tra tất định, so khớp nguyên cụm có dấu; với cụm từ hai chữ trở lên thì viết không dấu cũng bị bắt. Không bắt nhầm kiểu "gần" ↔ "gan", "thân" ↔ "thận", "gia đình" ↔ "giá".
- Giá nêu trong bài (65.000đ, 65k, 65 nghìn) phải khớp `list_price` trên website.
- Bộ phân loại rủi ro là bước phụ, dùng hồ sơ model `cheap`. Lỗi model → coi là "chưa rõ" → Owner duyệt (không tự cho qua).
- Từ điển sửa được trong dashboard (chỉ Owner), có ô "Thử một đoạn văn".

**Hàng chờ và lịch đăng (`app/content/publishing.py`, migration `0006_publishing`)**
- Lịch 3 giai đoạn đúng bảng ADR-16, là cài đặt (không hardcode). Khung 7:00–21:30, cách nhau ≥ 3 giờ, ngày nghỉ.
- Worker kiểm hàng chờ mỗi 30 giây:
  - máy tắt qua giờ đăng hơn 30 phút → **không đăng muộn**, xếp sang khung kế tiếp;
  - website báo hết hạn mức hoặc ngoài giờ → xếp lại; dữ liệu nguồn đổi, khóa sai → chặn; lỗi mạng → thử lại tối đa 5 lần.
- Tự lên giai đoạn (2 tuần rồi 4 tuần, có bài đăng, tỉ lệ gỡ < 10%) và báo Telegram. Owner gỡ ≥ 2 bài trong 7 ngày → lùi một giai đoạn.
- Bài bị gỡ → "Bài học: bài bị gỡ" (kèm lý do) vào trí nhớ riêng của agent viết. Góp ý → "Bài học: góp ý".

**Telegram có nút (`app/telegram/buttons.py`)**
- Nút Duyệt/Từ chối cho yêu cầu duyệt rủi ro thấp/vừa; Gỡ bài/Góp ý cho bài đã đăng. Việc rủi ro cao **không có nút**, chỉ duyệt trên dashboard + 2FA.
- Mỗi nút là một mã ngẫu nhiên lưu trong CSDL, kèm chữ ký HMAC; dùng một lần; gắn đúng chat; digest nội dung phải khớp; bấm một nút thì các nút cùng việc hết hiệu lực. Chỉ chat có quyền duyệt mới nhận nút.
- Lệnh `/tamdung xuatban` và `/tieptuc xuatban` (chỉ chat có quyền duyệt); `/trangthai` hiện giai đoạn và tình trạng tạm dừng.

**Control Center**
- Trang **Xuất bản** (thanh bên) có các tab:
  - Sắp đăng, Đã đăng, Bị chặn (kèm lý do; nút Gỡ bài/Hủy bài, Góp ý);
  - Lịch đăng bài;
  - Content Gate.
  Có nút **Tạm dừng xuất bản**.
- **Cài đặt → Website**: địa chỉ và 3 khóa (đọc, gửi bản nháp, xuất bản). Khóa mã hóa, chỉ hiện 4 ký tự cuối; đổi địa chỉ hay khóa phải xác thực lại. Có nút "Kiểm tra kết nối".
- Hộp **Giao việc** có thêm loại việc "Viết FAQ/blog và đăng lên website".

### Kiểm chứng

| Bộ test | Đạt |
|---|---|
| `test_publishing.py`: Content Gate, khung giờ, IT-PUB-01…07, IT-LG-02, bắt buộc review của cấp trên, IT-PUB-01/02 với **website thật** | 12 |
| `test_api_publishing.py`: Cài đặt → Website (khóa không bao giờ trả về), lịch đăng, Content Gate, tạm dừng, audit | 2 |
| `web/tests/acceptance.php` (gồm AT-09') | 27 ca |

- Toàn bộ backend: **165 test đạt** khi có website thật. Không có website thật thì 164 đạt, 1 bỏ qua (CI luôn dựng website thật).
- ruff, ruff format, mypy strict đều sạch. Frontend: tsc, eslint, build đạt.
- **E2E đạt.** Luồng thêm, chạy với "website giả" `e2e/fake_site.py` (chỉ trong `e2e/`):
  1. nhập địa chỉ và 3 khóa; khóa không hiện lại trên trang; "Kiểm tra kết nối" thấy 1 sản phẩm;
  2. giao Nội dung viết FAQ có đăng;
  3. Giám đốc Marketing duyệt review;
  4. bài vào lịch 11:30 và hiện ở tab Sắp đăng;
  5. thử Content Gate với "chữa bệnh… cam kết 100%" → bị chặn;
  6. tạm dừng rồi cho chạy lại.
- RAM: không thêm dịch vụ. Worker `worker` chạy thêm vòng hàng chờ xuất bản; RSS đo lại khi rảnh vẫn khoảng 136 MB (giới hạn 384 MB).

### Lệch so với kế hoạch (ghi trung thực)

| Kế hoạch | Thực tế | Lý do |
|---|---|---|
| Từ điển Content Gate là `shared_knowledge` loại `policy` (SECURITY_PLAN §6.3) | Là cài đặt `content_gate`, chỉ Owner sửa, có audit | Từ điển là luật cứng, cần đọc nhanh, không cần truy hồi ngữ nghĩa. Đưa vào trí nhớ chung khi Learning Engine (Sprint 5) đề xuất thêm cụm |
| Đối chiếu giá, **thành phần, quy cách**, khuyến mãi với catalog | Đối chiếu **giá**. Khuyến mãi luôn cần Owner duyệt. Thành phần và quy cách chưa đối chiếu | Catalog của website chưa có trường thành phần có cấu trúc. Ghi vào việc của 4c/Sprint 5 |
| Bảng `publications`, `publication_queue`, `publish_schedule`, `telegram_actions` | Gộp thành `publish_queue`; lịch đăng là cài đặt; nút là `telegram_buttons` (+ `telegram_prompts`) | Một dòng đi suốt đời bài, ít bảng hơn. DATABASE_SCHEMA đã sửa |
| Lịch đăng ở *Cài đặt → Lịch đăng bài* | Ở trang **Xuất bản → Lịch đăng bài** | Đặt cạnh hàng chờ để thấy ngay hệ quả khi đổi lịch |
| Hạn mức ngày đếm ở bảng `publications` và ở website | Máy: hạn mức theo agent của Policy Engine (`site.publish`, đếm trong `tool_invocations`) cộng lịch đăng (mỗi khung một bài). Website đếm tổng (lớp 5) | Không cần bảng đếm riêng; website vẫn là chốt chặn cuối, máy lỗi cũng không vượt được |
| Mã chống trùng gửi website | `co:<id hàng chờ>` (bài đăng), `co:draft:<id>` (bài bị chặn) | Theo IMPLEMENTATION_PLAN: tiền tố `co:` để không trùng dịch vụ cũ |

### Việc còn lại của Sprint 4

- 4c:
  - CEO → Director → SEO + Content trên dữ liệu thật;
  - giải quyết bất đồng (IT-A2A-03);
  - Evaluation bản đầu;
  - bản giọng văn thương hiệu để Owner duyệt;
  - IT-ORCH-01/02, AC-BRAIN-01;
  - đối chiếu thành phần/quy cách khi website có dữ liệu có cấu trúc.
- Giờ vàng riêng của xưởng: Data Analyst tính lại sau 4 tuần chạy thật (ADR-16).
- Số liệu chi phí 1 tuần chạy thử: cần Owner chạy trên máy với khóa API thật, sau 4c.
