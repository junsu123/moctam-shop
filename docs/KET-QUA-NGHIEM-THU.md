# Kết quả nghiệm thu tự động

- Thời điểm chạy: 26/11/2026 04:26 (giờ Việt Nam)
- Môi trường: PHP 8.3.6, 10.11.14-MariaDB-0ubuntu0.24.04.1
- Lệnh: `XUONG_DB=xuong_test php tests/acceptance.php`
- Tổng: **21/21 ca đạt**

| Mã | Kịch bản | Kết quả | Ghi chú | ms |
|---|---|---|---|---|
| BR-01 | Công thức tổng: 180.000 − 20.000 + 25.000 = 185.000 ₫ | **ĐẠT** | đơn TM261126MC4U = 185.000 ₫ | 18 |
| BR-02 | Voucher: đơn tối thiểu tính trên hàng đủ điều kiện sau Flash Sale; giảm ≤ tiền hàng đủ điều kiện | **ĐẠT** |  | 7 |
| BR-03 | Mỗi SKU tối đa một Flash Sale hiệu lực tại một thời điểm | **ĐẠT** | chồng lấn bị từ chối, nối tiếp được chấp nhận | 71 |
| AT-01 | Hai khách đặt cùng SKU chỉ còn 1 đơn vị (song song) | **ĐẠT** | 1 đơn thành công, 1 đơn nhận OUT_OF_STOCK, tồn khả dụng = 0 | 627 |
| AT-02 | Flash Sale kết thúc sau khi khách xem báo giá | **ĐẠT** | QUOTE_CHANGED → khách xác nhận → tạo đơn 100.000 ₫ | 10 |
| AT-03 | Mạng ngắt sau khi tạo đơn, khách gửi lại cùng yêu cầu | **ĐẠT** | gửi lại tuần tự và 3 yêu cầu trùng đồng thời đều trả 1 mã đơn; khóa trùng khác nội dung → IDEMPOTENCY_CONFLICT | 635 |
| AT-04 | Hai đơn dùng lượt voucher cuối cùng (song song) | **ĐẠT** | một đơn giữ lượt; đơn còn lại nhận QUOTE_CHANGED (VOUCHER_EXHAUSTED) | 724 |
| AT-05 | VietQR chuyển thiếu / chuyển sau khi đơn hết hạn | **ĐẠT** | thiếu tiền → sai lệch underpaid, chặn xác nhận; tiền sau hủy → after_cancel, đơn giữ trạng thái Đã hủy | 122 |
| AT-06 | Hủy trước khi xuất / hàng quay về sau giao thất bại | **ĐẠT** | hủy trước xuất: tồn giữ 3 → 0; hoàn hàng 2 (1 đạt, 1 hỏng): tồn 8 → 9 | 113 |
| AT-07 | Nhân viên kho thử duyệt hoàn tiền khi chưa được cấp quyền | **ĐẠT** | máy chủ trả FORBIDDEN, số liệu không đổi; tổng hoàn không vượt tiền thực nhận | 20 |
| AT-08a | Con trỏ đồng bộ theo thứ tự commit, nhận cả cập nhật đơn cũ | **ĐẠT** | seq A=26 commit trước B=27; con trỏ hết hạn → 410 CURSOR_EXPIRED | 1318 |
| AT-09 | AI gửi bản nháp trong lúc giá sản phẩm thay đổi | **ĐẠT** | bản nháp chờ duyệt; chat trả 72.000 ₫ (giá hiện hành) thay vì 65.000 ₫ trong bản nháp | 16 |
| AT-10 | Máy cá nhân tắt / API LLM lỗi: website vẫn bán, chat dùng FAQ hoặc kênh hỗ trợ | **ĐẠT** | FAQ khớp (điểm 0.3567), câu lạ → hotline; đơn TM261126FMKH tạo bình thường | 14 |
| AT-11 | Sao lưu và khôi phục sang CSDL kiểm thử | **ĐẠT** | sao lưu + khôi phục 0.3s; danh mục, ảnh, đơn, tồn, giao dịch khớp | 273 |
| EX-01 | Tác vụ hết hạn COD 48 giờ; giải phóng tồn và lượt voucher | **ĐẠT** |  | 37 |
| EX-02 | Báo lỗi cạnh trường nhập & vùng chưa phục vụ | **ĐẠT** |  | 1 |
| EX-03 | Lọc HTML, VietQR CRC, tìm kiếm có dấu/không dấu, SKU | **ĐẠT** |  | 4 |
| EX-04 | Nội dung: chờ duyệt → xuất bản; địa chỉ cố định sau khi xuất bản | **ĐẠT** |  | 75 |
| EX-05 | BM25 PHP khớp với Python (cùng điểm chuẩn hóa) | **ĐẠT** | điểm=0.2971 (đối chiếu với ai/tests) | 0 |
| EX-07 | Trang Chính sách bảo mật thông tin & Điều khoản sử dụng: có sẵn, chèn cấu hình an toàn, không ghi đè trang đã sửa | **ĐẠT** | hai trang xuất bản; biến cấu hình mã hóa an toàn; trang đã sửa được giữ nguyên | 26 |
| EX-06 | Làm mới dữ liệu trước khi chạy thật: sao lưu, xóa dữ liệu thử, giữ cấu hình; Python phải tải lại | **ĐẠT** | sao lưu truoc-lam-moi-20261125-212630-20b2.sql.gz; xóa 163 bản ghi thử; cấu hình giữ nguyên; nhân viên vận hành không có quyền | 286 |

AT-08 phía Python (mất kết nối, lô có sự kiện trùng, cập nhật đơn cũ) chạy bằng `pytest` trong thư mục `ai/` — xem `ai/tests/test_sync.py`.

## AT-08 phía Python và các kiểm thử dịch vụ AI

Lệnh: `cd ai && python -m pytest -v` — **15/15 đạt**.

| Kiểm thử | Nội dung |
|---|---|
| test_lost_connection_then_old_order_update_and_duplicates | Mất kết nối giữa hai lô: con trỏ chỉ dời tới lô đã ghi. Lô gửi lại có sự kiện trùng và cập nhật đơn cũ: mỗi sự kiện áp dụng đúng một lần, đơn cũ được cập nhật |
| test_stale_version_ignored | Sự kiện cũ hơn phiên bản đang có bị bỏ qua |
| test_batch_atomic_on_error | Lỗi giữa lô → hoàn tác toàn bộ, con trỏ giữ nguyên |
| test_cursor_expired_reloads_snapshot | 410 CURSOR_EXPIRED → tải lại bản chụp, đặt con trỏ = as_of_seq, phát lại sự kiện sau mốc |
| test_no_pii_columns | CSDL cục bộ không có cột tên/SĐT/địa chỉ |
| test_same_scores_as_php | BM25 Python và PHP cho điểm giống nhau (sai số < 1e-9) |
| test_faq_memory_first | Câu đã có FAQ → không gọi LLM; câu gần nghĩa được gom cụm; chạy lại không gọi LLM lần hai |
| test_label_change_retires_knowledge | Nhãn sản phẩm đổi phiên bản → tri thức cũ chuyển "retired" |
| test_llm_budget_and_redaction | Chặn khi chạm hạn mức ngày; SĐT/email bị che trước khi gửi LLM |
| test_crosssell_lift, test_care_due_and_consent | Gợi ý mua kèm theo lift; danh sách chăm sóc chỉ gồm khách đã đồng ý, bỏ khách đang có đơn mới |
| test_calibration_on_seed_faqs | Ngưỡng FAQ đạt độ chính xác ≥ 90% trên tập 40 câu tiếng Việt |

## Chạy thử tích hợp Python ↔ website

Trên CSDL thử với 54 đơn (51 đơn đã giao trong 90 ngày): `sync` tải bản chụp 54 đơn; `crosssell` gửi 14 gợi ý (website nhận 14, ở trạng thái chờ duyệt); `care` gửi danh sách 14 khách đã đồng ý; khóa `drafts:write` gọi `/api/sync/events` bị từ chối `403 FORBIDDEN`.

Hiệu chỉnh ngưỡng FAQ (`python -m xuong_ai calibrate`) trên 11 FAQ mẫu và 40 câu kiểm tra: **ngưỡng 0,10** cho độ chính xác 97%, độ phủ 91%, trả lời đạt 90%. Ca còn sai: 3 câu diễn đạt xa (để trống → chuyển hotline, an toàn) và 1 câu dễ nhầm ("bán sỉ cho quán cà phê" khớp FAQ cà phê). Ngưỡng cần chạy lại khi xưởng thay bộ FAQ thật.

## NFR-03 — đo tải sơ bộ (môi trường thử, KHÔNG tương đương production)

PHP 8.3 built-in server 20 tiến trình + MariaDB 10.11 cùng máy, 20 luồng đồng thời:

| Loại | Số yêu cầu | p50 | p95 | Mục tiêu p95 |
|---|---|---|---|---|
| Đọc trang chủ, danh mục, tìm kiếm, chi tiết sản phẩm | 800 | 37 ms | 87 ms | ≤ 1 giây |
| Tạo đơn (giao dịch giữ tồn + sự kiện đồng bộ) | 60 | 85 ms | 125 ms | ≤ 2 giây |

Không có mã đơn trùng, tồn khả dụng không âm. Cần đo lại trên gói Hostinger thực tế với dữ liệu đại diện trước khi mở bán (xem docs/TRIEN-KHAI-HOSTINGER.md §8).

## Tương thích PHP 8.0

Mã không dùng tính năng riêng của PHP 8.1+ (`never`, `readonly` đã được thay). Toàn bộ tệp PHP qua kiểm tra cú pháp bằng **PHP 8.0.7**. Bộ nghiệm thu ở trên chạy trên PHP 8.3; chưa chạy được trên 8.0 vì bản PHP 8.0 dùng để kiểm tra thiếu pdo_mysql/mbstring. PHP 8.0 đã hết hỗ trợ bảo mật từ 11/2023 — dùng để chạy thử được, production nên dùng 8.2 hoặc 8.3.
