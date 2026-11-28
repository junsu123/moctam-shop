# Báo cáo Sprint 3: Memory System

Thời gian: 27/11/2026. Owner duyệt "Sprint 3" sau khi gộp PR #10.

Sprint này cho mỗi agent một **trí nhớ có phân quyền**:
- agent nhớ trải nghiệm riêng của mình;
- đọc được kiến thức của phòng ban và kiến thức chung;
- không đọc được trí nhớ của agent khác, kể cả khi mã ứng dụng có lỗi (Row-Level Security của Postgres).

Truy hồi kết hợp tìm theo từ khóa (gõ có dấu, không dấu, viết tắt đều được) và tìm theo nghĩa (vector). Control Center có trang **Trí nhớ** và tab **Trí nhớ** trong trang từng agent.

## Đã xong (kèm bằng chứng)

**Lược đồ (`0004_memory`)**
- `agent_memories`: bảng gốc cho 4 loại trí nhớ.
  - Phạm vi `owner_scope`: `agent:<key>`, `dept:<phòng>`, `company`, `owner_only`.
  - Có nguồn, độ tin cậy của nguồn, độ tự tin, trạng thái (ứng viên → đã kiểm chứng → đang dùng → lỗi thời → nghỉ hưu), hiệu lực từ/đến, số lần hữu ích.
  - Chống trùng theo `(phạm vi, mã băm nội dung)`.
- Bảng chi tiết: `episodic_memories` (task, kết quả, chi phí), `semantic_memories` (mệnh đề, bằng chứng, mức bằng chứng), `procedural_memories` (quy trình có phiên bản).
- `embedding_models` + `memory_embeddings`: mỗi model một chỉ mục HNSW riêng, đổi model không phải đổi bảng.
- `memory_access_log`: mỗi lượt truy hồi ghi lại agent nào lấy mục nào, cho việc gì, hạng mấy, điểm bao nhiêu.
- View `shared_knowledge`.

**Phân quyền hai lớp**
- Hai vai trò Postgres: `aico_agent` (đọc trong phạm vi, chỉ ghi trải nghiệm vào vùng của chính mình) và `aico_learning` (ghi kiến thức, quy trình vào phạm vi được giao).
- `store.acting_as` đổi vai trò trong giao dịch và **kiểm lại** vai trò đã đổi thật chưa; chưa đổi được thì dừng (`RLS_NOT_ACTIVE`).
- Phạm vi theo sơ đồ tổ chức:
  - agent: vùng riêng + phòng mình + chung;
  - giám đốc phòng: thêm vùng riêng của nhân viên trực tiếp;
  - CEO: thêm mọi phòng;
  - chỉ Owner thấy `owner_only`.

**Truy hồi lai (`app/memory/retrieval.py`)**
- Chuẩn hóa tiếng Việt giống hệt bản mẫu `ai/xuong_ai/textnorm.py`: bỏ dấu, tách từ, mở rộng viết tắt ("sp" → "sản phẩm", "ko" → "không").
- Từ khóa: tsvector + trigram (bắt lỗi gõ), hai tầng, chi phí có trần.
- Vector: OpenAI `text-embedding-3-small` 512 chiều, gọi qua Model Gateway (che SĐT/email trước khi gửi, ghi chi phí, kiểm ngân sách). Chưa có khóa thì trả `not_configured` và chỉ tìm theo từ khóa.
- Gộp hai danh sách bằng RRF, nhân trọng số:
  - độ mới (trải nghiệm: chu kỳ bán rã 60 ngày);
  - độ tự tin;
  - độ tin cậy của nguồn: Owner 1; nội bộ 0,9; nguồn ngoài đã kiểm chứng 0,8; chưa kiểm chứng 0,5.
- Ngân sách token theo bộ não của agent, chia theo nhóm (quy trình, trải nghiệm, kiến thức, chung). Khử trùng gần giống bằng MMR.
- `mark_used`: mục được dùng trong kết quả cuối thì tăng `usefulness`.
- Working memory trên Redis cho từng task (hết hạn sau 7 ngày).

**Nhúng vector**
- Worker `memory` (compose), mỗi phút nhúng tối đa 256 mục mới. Lệnh tay: `python -m app.cli embed-memories`.
- Đổi model: bật model mới → nhúng lại → xóa vector cũ chỉ khi model mới đã nhúng đủ.

**API**
- `GET /memory/stats`, `GET /memory` (lọc phạm vi, loại, nguồn, trạng thái, agent, từ khóa), `GET /memory/{id}` (chi tiết, nhật ký truy hồi, vector).
- `POST /memory`: Owner thêm kiến thức hoặc quy trình. `POST /memory/{id}/retire`: cho nghỉ hưu (ghi audit).
- `POST /agents/{key}/memory/search`: thử truy hồi đúng như agent sẽ thấy (không ghi nhật ký).
- `POST /memory/embed`: nhúng ngay.

**Control Center**
- Trang **Trí nhớ** (thanh bên):
  - thẻ số liệu: tổng số mục theo loại, lượt truy hồi hôm nay, tình trạng tìm theo nghĩa (đã nhúng bao nhiêu, nút "Nhúng ngay");
  - 4 tab: Kiến thức chung, Theo phòng ban, Riêng từng agent, Chỉ Owner;
  - hộp "Thêm kiến thức".
- Trang agent có thêm tab **Trí nhớ**:
  - "Thử truy hồi": gõ một yêu cầu, xem agent nhớ ra những gì và **vì sao** (hạng từ khóa, hạng vector, trọng số, điểm, số token);
  - danh sách trí nhớ agent đọc được, mở từng mục xem nội dung, nhật ký truy hồi, cho nghỉ hưu.

**Kiểm chứng**

| Bộ test | Số test đạt |
|---|---|
| `test_memory.py`: UT-MEM-01…10, IT-DB-02 (2 test), IT-VEC-01, IT-VEC-02, tìm theo nghĩa không chung từ | 16 |
| `test_api_memory.py`: API trí nhớ, quyền | 2 |

- Tổng **130 test backend đạt**; ruff, ruff format, mypy strict đều sạch.
- Frontend: tsc, eslint, build đạt.
- **E2E 1/1 đạt**, thêm: Owner thêm kiến thức chung; Chăm sóc khách gõ "sp co giao trong ngay ko" (không dấu, viết tắt) và nhớ ra đúng "Chính sách giao hàng", có giải thích điểm.

## PT-03: hiệu năng truy hồi

Công cụ đo: `backend/bench/pt03_memory.py` (chạy trên CSDL riêng tên chứa `bench`). Dữ liệu tổng hợp từ từ vựng của xưởng; vector 512 chiều sinh quanh 500 cụm. Mỗi lượt là truy hồi thật: đổi vai trò + RLS, từ khóa + vector, chấm điểm, ngân sách token, MMR, ghi nhật ký. Postgres cấu hình như compose (`shared_buffers=512MB`, `work_mem=8MB`), máy đo 2 nhân.

| Số mục trí nhớ | 20 nghìn | 200 nghìn | 1 triệu |
|---|---|---|---|
| Truy hồi lai (từ khóa + vector), p50 / **p95** | – | 77 / **115 ms** | 186 / **283 ms** |
| Chỉ từ khóa (chưa có khóa OpenAI), p50 / **p95** | – | 50 / **82 ms** | 123 / **174 ms** |
| Recall@10 tìm vector trong phạm vi agent | – | 0,90 | 0,79 |
| Dung lượng: trí nhớ + vector + chỉ mục HNSW | 38 + 108 + 52 MB | 275 + 1.081 + 521 MB | 1.448 + 5.403 + 2.604 MB |
| Bản đầu tiên (trước tối ưu), p95 | 755 ms | khoảng 1.300 ms | – |

Mục tiêu PT-03 (TEST_PLAN): 1 triệu mục, p95 < 150 ms.
- **Đạt ở 200 nghìn mục** (115 ms).
- **Chưa đạt ở 1 triệu** (283 ms). Lý do: chỉ mục vector 2,6 GB và bảng 5,4 GB không nằm gọn trong bộ đệm của Postgres (giới hạn 1 GB RAM trong ngân sách 6 GB). Máy đo còn có bộ đệm hệ điều hành ~6 GB, nên trên máy Owner với container 1 GB, số đo ở 1 triệu sẽ còn chậm hơn.
- Recall 0,79–0,90 đo trên vector tổng hợp phân cụm dày (ca khó cho HNSW). Embedding văn bản thật thường cho recall cao hơn. Thêm nữa, mục bị HNSW bỏ sót vẫn có thể được tìm thấy qua nhánh từ khóa.

Ba chỗ chậm đã tìm ra và sửa trong Sprint:
1. Dưới RLS, Postgres không dùng chỉ mục cho phép so từ khóa: chuyển bước tìm id vào hàm `SECURITY DEFINER` tự lọc phạm vi (xem DECISIONS).
2. MMR tính lại độ giống từ đầu sau mỗi lần chọn: đổi sang cập nhật dần, 520 ms còn 20 ms.
3. Nhật ký truy hồi ghi từng dòng (khoảng 90 câu lệnh mỗi lượt): gộp thành một câu.

Ước lượng khối lượng thật: 15 agent, mỗi agent vài chục trải nghiệm mỗi ngày, cộng kiến thức → khoảng 100–300 nghìn mục mỗi năm. Kế hoạch giữ dưới mức đã đạt:
- Sprint 5 (Learning Engine) gộp trải nghiệm cũ thành bài học rồi cho nghỉ hưu; nghỉ hưu thì xóa vector;
- lưu vector dạng `halfvec` (pgvector ≥ 0.7, ảnh Docker đã có): giảm một nửa dung lượng;
- khi nâng máy lên 32 GB RAM: cho Postgres 2–3 GB.

## Lệch so với kế hoạch (ghi trung thực)

| Kế hoạch | Thực tế | Lý do / xử lý |
|---|---|---|
| | Số mục trí nhớ | 20 nghìn | 200 nghìn | 1 triệu |
|---|---|---|---|
| Truy hồi lai (từ khóa + vector), p50 / **p95** | – | 77 / **115 ms** | 186 / **283 ms** |
| Chỉ từ khóa (chưa có khóa OpenAI), p50 / **p95** | – | 50 / **82 ms** | 123 / **174 ms** |
| Recall@10 tìm vector trong phạm vi agent | – | 0,90 | 0,79 |
| Dung lượng: trí nhớ + vector + chỉ mục HNSW | 38 + 108 + 52 MB | 275 + 1.081 + 521 MB | 1.448 + 5.403 + 2.604 MB |
| Bản đầu tiên (trước tối ưu), p95 | 755 ms | khoảng 1.300 ms | – |

Mục tiêu PT-03 (TEST_PLAN): 1 triệu mục, p95 < 150 ms.
- **Đạt ở 200 nghìn mục** (115 ms).
- **Chưa đạt ở 1 triệu** (283 ms). Lý do: chỉ mục vector 2,6 GB và bảng 5,4 GB không nằm gọn trong bộ đệm của Postgres (giới hạn 1 GB RAM trong ngân sách 6 GB). Máy đo còn có bộ đệm hệ điều hành ~6 GB, nên trên máy Owner với container 1 GB, số đo ở 1 triệu sẽ còn chậm hơn.
- Recall 0,79–0,90 đo trên vector tổng hợp phân cụm dày (ca khó cho HNSW). Embedding văn bản thật thường cho recall cao hơn. Thêm nữa, mục bị HNSW bỏ sót vẫn có thể được tìm thấy qua nhánh từ khóa.

Ba chỗ chậm đã tìm ra và sửa trong Sprint:
1. Dưới RLS, Postgres không dùng chỉ mục cho phép so từ khóa: chuyển bước tìm id vào hàm `SECURITY DEFINER` tự lọc phạm vi (xem DECISIONS).
2. MMR tính lại độ giống từ đầu sau mỗi lần chọn: đổi sang cập nhật dần, 520 ms còn 20 ms.
3. Nhật ký truy hồi ghi từng dòng (khoảng 90 câu lệnh mỗi lượt): gộp thành một câu.

Ước lượng khối lượng thật: 15 agent, mỗi agent vài chục trải nghiệm mỗi ngày, cộng kiến thức → khoảng 100–300 nghìn mục mỗi năm. Kế hoạch giữ dưới mức đã đạt:
- Sprint 5 (Learning Engine) gộp trải nghiệm cũ thành bài học rồi cho nghỉ hưu; nghỉ hưu thì xóa vector;
- lưu vector dạng `halfvec` (pgvector ≥ 0.7, ảnh Docker đã có): giảm một nửa dung lượng;
- khi nâng máy lên 32 GB RAM: cho Postgres 2–3 GB._ROW |
| `memory_embeddings` mỗi model một bảng con (DATABASE_SCHEMA) | Một bảng, mỗi model một chỉ mục HNSW một phần | Đổi model đơn giản hơn; DATABASE_SCHEMA đã sửa |
| Truy vấn trí nhớ chạy hoàn toàn dưới RLS | Bước tìm id chạy trong 2 hàm `SECURITY DEFINER` tự lọc phạm vi của phiên; đọc nội dung vẫn dưới RLS | Dưới RLS Postgres không dùng chỉ mục cho `@@`/`<%`: 1,3–2 giây/lượt ở 200 nghìn mục. Có test chứng minh hàm không lộ trí nhớ ngoài phạm vi (IT-DB-02) |
| `experience_records` | Chưa tạo | Cần Task Engine (Sprint 4) và Evaluation (Sprint 5) |
| Embedding cục bộ hoặc đám mây | Chỉ đám mây (OpenAI) | Q-T3a: RX 560 không chạy được model cục bộ |

## Việc chuyển sang Sprint sau (đã ghi, chưa làm)

- Sprint 4: runtime agent gọi `retrieve` trước khi làm task, `remember_episode` sau khi xong, `mark_used` khi nộp kết quả; working memory lưu checkpoint theo task.
- Sprint 5: Learning Engine ghi kiến thức qua `aico_learning` (hàng chờ ứng viên → kiểm chứng → duyệt); `experience_records`.
- Phân vùng `memory_access_log` theo tháng khi bảng vượt vài triệu dòng.

## Owner làm gì để dùng

1. Nhập khóa API OpenAI ở **Cài đặt → Nhà cung cấp AI** (nếu chưa). Không có khóa thì trí nhớ vẫn tìm được theo từ khóa.
2. Vào **Trí nhớ → Thêm kiến thức**: chính sách giao hàng, đổi trả, câu chuyện thương hiệu, mục tiêu quý… Đây là kiến thức nền mọi agent dùng từ Sprint 4.
3. Vào trang một agent → tab **Trí nhớ** → "Thử truy hồi" để xem agent sẽ nhớ ra gì.

## Chi phí LLM trong Sprint

- Nhúng vector: 0,02 USD / 1 triệu token. 1.000 mục kiến thức (khoảng 150 nghìn token) tốn khoảng 0,003 USD.
- Mỗi lượt truy hồi nhúng câu hỏi: khoảng 20 token, gần như bằng 0.
- Phát triển và test không gọi API thật (dùng bộ giả lập trong `tests/`).
