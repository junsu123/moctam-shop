# Website bán hàng + dịch vụ AI cục bộ — "Xưởng Trà Mộc" (tên tạm)

Mã nguồn hiện thực *Đặc tả phần mềm website bán hàng v1.0*: bán trực tiếp trà túi lọc, bột ngũ cốc, bột thiên nhiên và cà phê, với một bên bán, một kho, thanh toán COD hoặc VietQR.

| Thư mục | Nội dung | Chạy ở đâu |
|---|---|---|
| `web/` | **Giai đoạn 1**: website cửa hàng + trang quản trị. PHP 8, PDO, MySQL/MariaDB, Tailwind đã biên dịch, JS thuần | Hostinger |
| `ai/` | **Giai đoạn 2**: dịch vụ AI. Python 3.11, SQLite, BM25, Claude/OpenAI tùy chọn | Máy cá nhân |
| `docs/` | Thiết kế kỹ thuật, API, triển khai Hostinger, sao lưu/khôi phục, kết quả nghiệm thu, ảnh màn hình | — |

## Đọc theo thứ tự

1. `docs/THIET-KE.md`: kiến trúc, sơ đồ dữ liệu, luồng đặt hàng, trạng thái đơn, đối soát, đồng bộ, AI, bảng truy vết FR/NFR → mã nguồn.
2. `docs/TRIEN-KHAI-HOSTINGER.md`: cài đặt từng bước, cron, cấu hình trước khi mở bán.
3. `docs/KET-QUA-NGHIEM-THU.md`: AT-01…AT-11 (19/19 ca website + 15/15 kiểm thử Python đạt), đo tải.
4. `docs/API.md`, `docs/SAO-LUU-KHOI-PHUC.md`, `ai/README.md`.

## Chạy thử trên máy (5 phút)

Cần PHP 8.1+ (có pdo_mysql, mbstring, intl, dom) và MySQL hoặc MariaDB.

```bash
cd web
cp app/config.sample.php app/config.php        # điền db; đặt 'secure' => false khi chạy http://localhost
mysql -e "CREATE DATABASE xuong_dev CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
php bin/migrate.php
php bin/seed.php --demo-users                  # dữ liệu mẫu + tài khoản thử (mật khẩu Demo@12345)
php bin/seed_orders.php                        # (tùy chọn) đơn lịch sử để thử AI
php -S localhost:8080 -t public_html tests/devrouter.php
```

Sau đó mở `http://localhost:8080` để xem cửa hàng, và `http://localhost:8080/admin` để vào quản trị. Tài khoản quản trị viên là `admin@xuong.local`. Các vai trò thử khác: `vanhanh@`, `kho@`, `doisoat@`, `noidung@` (đều đuôi `xuong.local`).

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
- **Chính sách giao hàng, thanh toán, đổi trả, bảo mật**: hiện là bản mẫu. Cần rà soát yêu cầu về TMĐT, thực phẩm, hóa đơn và dữ liệu cá nhân.
- **Quản lý lô và hạn dùng**: chọn website hay sổ nghiệp vụ. Nếu chọn website, xem `docs/THIET-KE.md` §3 để bổ sung migration.
- **Nhân sự đối soát**: phân quyền nhân sự theo từng vai trò.
- **Ngưỡng chat**: mặc định 0,10, đã hiệu chỉnh trên FAQ mẫu. Chạy lại `python -m xuong_ai calibrate` sau khi nhập FAQ thật.

## Ngoài phạm vi v1

Theo đặc tả, các mục sau để giai đoạn "mở rộng sau": tích hợp API hãng vận chuyển, đối soát ngân hàng tự động, đánh giá từ đơn đã mua, và combo có tồn kho theo từng thành phần. Lược đồ dữ liệu hiện tại đã sẵn chỗ để mở rộng cho các mục này: `payment_receipts.source` cho ngân hàng, `orders.carrier_name` và `orders.tracking_code` cho vận chuyển.
