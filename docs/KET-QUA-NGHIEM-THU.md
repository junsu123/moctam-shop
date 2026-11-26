# Kết quả nghiệm thu tự động

- Thời điểm chạy: 26/11/2026 14:47 (giờ Việt Nam)
- Môi trường: PHP 8.3.6, 10.11.14-MariaDB-0ubuntu0.24.04.1
- Lệnh: `XUONG_DB=xuong_test php tests/acceptance.php`
- Tổng: **25/25 ca đạt**

| Mã | Kịch bản | Kết quả | Ghi chú | ms |
|---|---|---|---|---|
| BR-01 | Công thức tổng: 180.000 − 20.000 + 25.000 = 185.000 ₫ | **ĐẠT** | đơn TM261126XQBB = 185.000 ₫ | 11 |
| BR-02 | Voucher: đơn tối thiểu tính trên hàng đủ điều kiện sau Flash Sale; giảm ≤ tiền hàng đủ điều kiện | **ĐẠT** |  | 5 |
| BR-03 | Mỗi SKU tối đa một Flash Sale hiệu lực tại một thời điểm | **ĐẠT** | chồng lấn bị từ chối, nối tiếp được chấp nhận | 54 |
| AT-01 | Hai khách đặt cùng SKU chỉ còn 1 đơn vị (song song) | **ĐẠT** | 1 đơn thành công, 1 đơn nhận OUT_OF_STOCK, tồn khả dụng = 0 | 625 |
| AT-02 | Flash Sale kết thúc sau khi khách xem báo giá | **ĐẠT** | QUOTE_CHANGED → khách xác nhận → tạo đơn 100.000 ₫ | 10 |
| AT-03 | Mạng ngắt sau khi tạo đơn, khách gửi lại cùng yêu cầu | **ĐẠT** | gửi lại tuần tự và 3 yêu cầu trùng đồng thời đều trả 1 mã đơn; khóa trùng khác nội dung → IDEMPOTENCY_CONFLICT | 632 |
| AT-04 | Hai đơn dùng lượt voucher cuối cùng (song song) | **ĐẠT** | một đơn giữ lượt; đơn còn lại nhận QUOTE_CHANGED (VOUCHER_EXHAUSTED) | 624 |
| AT-05 | VietQR chuyển thiếu / chuyển sau khi đơn hết hạn | **ĐẠT** | thiếu tiền → sai lệch underpaid, chặn xác nhận; tiền sau hủy → after_cancel, đơn giữ trạng thái Đã hủy | 95 |
| AT-06 | Hủy trước khi xuất / hàng quay về sau giao thất bại | **ĐẠT** | hủy trước xuất: tồn giữ 3 → 0; hoàn hàng 2 (1 đạt, 1 hỏng): tồn 8 → 9 | 95 |
| AT-07 | Nhân viên kho thử duyệt hoàn tiền khi chưa được cấp quyền | **ĐẠT** | máy chủ trả FORBIDDEN, số liệu không đổi; tổng hoàn không vượt tiền thực nhận | 19 |
| AT-08a | Con trỏ đồng bộ theo thứ tự commit, nhận cả cập nhật đơn cũ | **ĐẠT** | seq A=26 commit trước B=27; con trỏ hết hạn → 410 CURSOR_EXPIRED | 1313 |
| AT-09 | AI gửi bản nháp trong lúc giá sản phẩm thay đổi | **ĐẠT** | bản nháp chờ duyệt; chat trả 72.000 ₫ (giá hiện hành) thay vì 65.000 ₫ trong bản nháp | 13 |
| AT-10 | Máy cá nhân tắt / API LLM lỗi: website vẫn bán, chat dùng FAQ hoặc kênh hỗ trợ | **ĐẠT** | FAQ khớp (điểm 0.3567), câu lạ → hotline; đơn TM2611267GAM tạo bình thường | 11 |
| AT-11 | Sao lưu và khôi phục sang CSDL kiểm thử | **ĐẠT** | sao lưu + khôi phục 0.3s; danh mục, ảnh, đơn, tồn, giao dịch khớp | 292 |
| EX-01 | Tác vụ hết hạn COD 48 giờ; giải phóng tồn và lượt voucher | **ĐẠT** |  | 32 |
| EX-02 | Báo lỗi cạnh trường nhập & vùng chưa phục vụ | **ĐẠT** |  | 1 |
| EX-03 | Lọc HTML, VietQR CRC, tìm kiếm có dấu/không dấu, SKU | **ĐẠT** |  | 3 |
| EX-04 | Nội dung: chờ duyệt → xuất bản; địa chỉ cố định sau khi xuất bản | **ĐẠT** |  | 56 |
| EX-05 | BM25 PHP khớp với Python (cùng điểm chuẩn hóa) | **ĐẠT** | điểm=0.2971 (đối chiếu với ai/tests) | 0 |
| EX-08 | Đăng nhập tùy chọn Google/Facebook: xác thực state/nonce/PKCE/appsecret_proof, liên kết theo email đã xác minh, đơn gắn tài khoản, xóa dữ liệu | **ĐẠT** | state dùng một lần, nonce/PKCE/hạn/issuer, appsecret_proof; email chưa xác minh không gộp; đơn khách lẻ không lộ; xóa theo yêu cầu Facebook có mã tra cứu | 130 |
| EX-09 | Quản trị tài khoản khách: phân quyền, tìm kiếm, khóa/mở khóa, buộc đăng xuất, gỡ liên kết, xóa thay khách; mở khóa nhân viên | **ĐẠT** | quyền accounts.manage; khóa chặn cả nhà cung cấp mới cùng email; phiên cũ bị vô hiệu và không liên kết được; không gỡ cách đăng nhập cuối; xóa có mã + nhật ký | 429 |
| EX-10 | Địa chỉ một cấp .html: dựng/giải link, đường dẫn duy nhất toàn site, chuyển hướng link cũ, gỡ trùng khi nâng cấp | **ĐẠT** | một cấp .html; duy nhất toàn site; link cũ → 301 đúng đích (kể cả mục bị đổi đường dẫn khi nâng cấp) | 19 |
| EX-11 | SEO trang khách: tiêu đề/mô tả, canonical trang phân trang, JSON-LD (Product, Breadcrumb, Organization), robots.txt, sitemap lastmod | **ĐẠT** | tiêu đề ≤60, mô tả ≤160; JSON-LD an toàn và đủ thuộc tính bắt buộc; canonical phân trang; robots + sitemap | 9 |
| EX-07 | Trang Chính sách bảo mật thông tin & Điều khoản sử dụng: có sẵn, chèn cấu hình an toàn, không ghi đè trang đã sửa | **ĐẠT** | hai trang xuất bản; biến cấu hình mã hóa an toàn; trang đã sửa được giữ nguyên | 17 |
| EX-06 | Làm mới dữ liệu trước khi chạy thật: sao lưu, xóa dữ liệu thử, giữ cấu hình; Python phải tải lại | **ĐẠT** | sao lưu truoc-lam-moi-20261126-074736-1cdd.sql.gz; xóa 199 bản ghi thử; cấu hình giữ nguyên; nhân viên vận hành không có quyền | 152 |

AT-08 phía Python (mất kết nối, lô có sự kiện trùng, cập nhật đơn cũ) chạy bằng `pytest` trong thư mục `ai/` — xem `ai/tests/test_sync.py`.
