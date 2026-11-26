# Website bán hàng + dịch vụ AI cục bộ — "Xưởng Trà Mộc" (tên tạm)

Mã nguồn hiện thực *Đặc tả phần mềm website bán hàng v1.0*: bán trực tiếp trà túi lọc, bột ngũ cốc, bột thiên nhiên và cà phê, với một bên bán, một kho, thanh toán COD hoặc VietQR.

| Thư mục | Nội dung | Chạy ở đâu |
|---|---|---|
| `web/` | **Giai đoạn 1**: website cửa hàng + trang quản trị. PHP 8.0+, PDO, MySQL/MariaDB, Tailwind đã biên dịch, JS thuần | Hostinger |
| `ai/` | **Giai đoạn 2**: dịch vụ AI. Python 3.11, SQLite, BM25, Claude/OpenAI tùy chọn | Máy cá nhân |
| `docs/` | Thiết kế kỹ thuật, API, triển khai Hostinger, sao lưu/khôi phục, kết quả nghiệm thu, ảnh màn hình | — |

## Cài đặt trên Hostinger — một dòng lệnh

1. Trong hPanel: chọn **PHP 8.2 hoặc 8.3**, tạo **một CSDL MySQL**, rồi bật **SSH Access**.
2. Mở SSH (hPanel → SSH Access → Terminal, hoặc dùng `ssh` từ máy), dán dòng sau rồi trả lời vài câu hỏi:

```bash
curl -fsSL https://raw.githubusercontent.com/junsu123/moctam-shop/main/install.sh | bash
```

Trình cài đặt tự tìm PHP, kiểm tra kết nối CSDL, đặt mã nguồn đúng chỗ (phần mã ứng dụng nằm ngoài `public_html`), tạo cấu hình với khóa bí mật ngẫu nhiên, tạo bảng, tạo tài khoản quản trị và đặt các tác vụ định kỳ. Nếu gói hosting không cho đặt cron qua SSH, trình cài in ra sẵn 2 dòng để bạn dán vào hPanel → Cron Jobs.

**Cập nhật phiên bản mới:** chạy lại đúng dòng lệnh trên. Trình cài tự sao lưu trước, giữ nguyên cấu hình, ảnh và dữ liệu, chỉ thay mã nguồn và nâng cấp CSDL.

> Dòng lệnh tải mã từ GitHub, nên repo cần để **Public**. Nếu chuyển repo sang Private, hãy tải tệp zip rồi làm theo phần cài thủ công trong `docs/TRIEN-KHAI-HOSTINGER.md`.

## Đọc theo thứ tự

1. `docs/THIET-KE.md`: kiến trúc, sơ đồ dữ liệu, luồng đặt hàng, trạng thái đơn, đối soát, đồng bộ, AI, bảng truy vết FR/NFR → mã nguồn.
2. `docs/TRIEN-KHAI-HOSTINGER.md`: cài đặt từng bước, cron, cấu hình trước khi mở bán.
3. `docs/KET-QUA-NGHIEM-THU.md`: AT-01…AT-11 (24/24 ca website + 15/15 kiểm thử Python đạt), đo tải.
4. `docs/API.md`, `docs/SAO-LUU-KHOI-PHUC.md`, `ai/README.md`.

## Chạy thử trên máy tính — một lệnh

Cần **PHP 8.0+** (khuyên dùng 8.2+) và **MySQL/MariaDB** đang chạy. Trên Windows, cách dễ nhất là cài [XAMPP](https://www.apachefriends.org) hoặc [Laragon](https://laragon.org), rồi bật MySQL. Mở cửa sổ lệnh tại thư mục mã nguồn và gõ:

```bash
php start-local.php
```

> Windows + XAMPP, nếu máy báo không nhận lệnh `php`: dùng `C:\xampp\php\php.exe start-local.php`

Lệnh này tự kiểm tra PHP, tìm MySQL (thử `root` không mật khẩu; nếu không vào được sẽ hỏi), tạo CSDL `moctam_local`, tạo bảng, nạp 16 sản phẩm mẫu và khoảng 40 đơn mẫu, tạo sẵn cấu hình cho dịch vụ AI, rồi mở trình duyệt tại `http://localhost:8000`.

- Quản trị: `http://localhost:8000/admin`, đăng nhập `admin@xuong.local`, mật khẩu `Demo@12345`. Có thêm 4 tài khoản để thử phân quyền: `vanhanh@`, `kho@`, `doisoat@`, `noidung@` (đều đuôi `xuong.local`, cùng mật khẩu).
- Thử dịch vụ AI: mở cửa sổ lệnh thứ hai, `cd ai`, chạy `python -m xuong_ai once sync`, rồi `python -m xuong_ai once crosssell`. Cần Python 3.11+.
- Dừng bằng Ctrl+C. Gõ lại lệnh là chạy tiếp, dữ liệu được giữ. Thêm `--reset` để làm lại từ đầu, hoặc `--port=8001` để đổi cổng.
- Chế độ chạy thử dùng `http` và bật hiển thị lỗi, **không dùng cấu hình này cho Hostinger**.

Chạy nghiệm thu (script sẽ **xóa và tạo lại** CSDL, nên tên CSDL phải chứa chữ `test`):

```bash
XUONG_DB=xuong_test php tests/acceptance.php
cd ../ai && python -m pytest -v
```

## Việc xưởng cần chốt trước khi mở bán

Đây là các mục theo đặc tả §8. Hệ thống đã có chỗ cấu hình cho từng mục.

- **Tên thương hiệu, hotline, Zalo, địa chỉ**: Quản trị → Cấu hình.
- **Tài khoản nhận VietQR**: mã BIN ngân hàng, số tài khoản, tên chủ tài khoản. Đặt thử một đơn nhỏ và quét mã bằng ứng dụng ngân hàng để kiểm tra.
- **Vùng giao và biểu phí**: bản mẫu có 4 vùng phủ 34 tỉnh/thành, phí 20–35 nghìn đồng.
- **Thời hạn**: báo giá 15 phút, giữ hàng VietQR 24 giờ, chờ xác nhận COD 48 giờ. Chỉnh theo lịch trực đối soát và tốc độ giao hàng.
- **Thông tin nhãn sản phẩm**: thành phần, dị ứng, cách dùng, bảo quản. Dữ liệu mẫu chỉ để minh họa, phải thay bằng nhãn thật, vì chat trích nguyên văn các mục này.
- **Thông tin pháp lý** (Quản trị → Cấu hình → Thông tin pháp lý): tên hộ kinh doanh hoặc doanh nghiệp, số ĐKKD/MST, ngày và nơi cấp, người đại diện, nơi đặt máy chủ. Các thông tin này hiện ở chân trang và được tự điền vào hai trang **Chính sách bảo mật thông tin** (`/bao-mat.html`) và **Điều khoản sử dụng** (`/dieu-khoan-su-dung.html`). Mục nào còn trống sẽ hiện "[chưa cập nhật: …]" trên trang, và trang Giám sát cảnh báo.
- **Hai trang pháp lý**: đã soạn đầy đủ theo Luật Bảo vệ dữ liệu cá nhân 91/2025/QH15, Nghị định 356/2025/NĐ-CP và Luật Thương mại điện tử 122/2025/QH15. Nên nhờ luật sư rà soát trước khi mở bán. Các trang giao hàng, thanh toán, đổi trả vẫn là bản mẫu, cần xưởng chỉnh lại.
- **Quản lý lô và hạn dùng**: chọn website hay sổ nghiệp vụ. Nếu chọn website, xem `docs/THIET-KE.md` §3 để bổ sung migration.
- **Nhân sự đối soát**: phân quyền nhân sự theo từng vai trò.
- **Ngưỡng chat**: mặc định 0,10, đã hiệu chỉnh trên FAQ mẫu. Chạy lại `python -m xuong_ai calibrate` sau khi nhập FAQ thật.

## Đăng nhập bằng Google / Facebook (tùy chọn)

Khách vẫn mua không cần tài khoản. Muốn bật nút đăng nhập: tạo ứng dụng Google/Facebook và điền khóa vào `app/config.php` theo [docs/TRIEN-KHAI-HOSTINGER.md §10](docs/TRIEN-KHAI-HOSTINGER.md#10-đăng-nhập-bằng-google--facebook-tùy-chọn). Chưa điền thì website không hiện nút.

Nhân viên quản lý các tài khoản này ở **Quản trị → Tài khoản khách**: tìm theo email/tên/SĐT, xem cách đăng nhập đã liên kết, buộc đăng xuất, tạm khóa, gỡ liên kết, xóa theo yêu cầu của khách. Tài khoản nhân viên bị tạm khóa do nhập sai mật khẩu được mở khóa ở **Quản trị → Tài khoản nhân viên**.

## Làm mới dữ liệu khi chạy thật

Trước ngày mở bán, vào Quản trị → **Làm mới dữ liệu** (hoặc chạy `php bin/reset_data.php`) để xóa toàn bộ đơn, khách, giao dịch thử và tùy chọn cả sản phẩm mẫu, voucher, blog/FAQ mẫu, tài khoản mẫu, nhật ký thử. Cấu hình, danh mục, vùng giao, trang chính sách và tài khoản quản trị được giữ nguyên. Hệ thống luôn sao lưu trước khi xóa. Chi tiết ở `docs/TRIEN-KHAI-HOSTINGER.md` §6 bước 8.

## Ngoài phạm vi v1

Theo đặc tả, các mục sau để giai đoạn "mở rộng sau": tích hợp API hãng vận chuyển, đối soát ngân hàng tự động, đánh giá từ đơn đã mua, và combo có tồn kho theo từng thành phần. Lược đồ dữ liệu hiện tại đã sẵn chỗ để mở rộng cho các mục này: `payment_receipts.source` cho ngân hàng, `orders.carrier_name` và `orders.tracking_code` cho vận chuyển.
