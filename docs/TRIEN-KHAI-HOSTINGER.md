# Hướng dẫn triển khai trên Hostinger

Áp dụng cho các gói Hostinger có PHP 8.0+ (khuyên dùng 8.2 hoặc 8.3) và MySQL/MariaDB, như Business Web Hosting hoặc Cloud. Trước khi cài, vào hPanel kiểm tra phiên bản PHP và MySQL của gói sẽ dùng.

## Cách nhanh: một dòng lệnh

Sau khi làm 3 việc ở mục 1 (chọn PHP 8.2/8.3, tạo CSDL, bật SSH), mở SSH rồi chạy:

```bash
curl -fsSL https://raw.githubusercontent.com/junsu123/moctam-shop/main/install.sh | bash
```

Trình cài đặt sẽ làm tự động các mục 2–5 bên dưới. Chạy lại cùng lệnh để **cập nhật**: trình cài tự sao lưu trước, rồi giữ nguyên cấu hình và dữ liệu. Muốn chạy không cần trả lời câu hỏi, đặt sẵn các biến trước lệnh:

```bash
DOMAIN=ten-mien.vn DB_NAME=u123_shop DB_USER=u123_shop DB_PASS='...' ADMIN_EMAIL=chu@ten-mien.vn ADMIN_PASS='...' SAMPLE=0 \
  bash -c "$(curl -fsSL https://raw.githubusercontent.com/junsu123/moctam-shop/main/install.sh)"
```

Sau khi cài, làm tiếp mục 6 (cấu hình nghiệp vụ). Phần còn lại của tài liệu là cách cài **thủ công**, dùng khi không có SSH hoặc khi repo để Private.

## 1. Chuẩn bị trên hPanel

1. **Websites → Quản lý → Advanced → PHP Configuration**: chọn PHP 8.2 hoặc 8.3, bật các extension `pdo_mysql`, `mbstring`, `intl`, `dom`, `fileinfo`, `gd`, `zip`.
2. **Databases → MySQL Databases**: tạo CSDL và người dùng, gán toàn quyền trên CSDL đó. Ghi lại tên CSDL, tên người dùng, mật khẩu và host (thường là `localhost`).
3. **Security → SSL**: cài SSL miễn phí cho tên miền. File `.htaccess` đã có sẵn quy tắc ép chuyển sang HTTPS.
4. **Advanced → SSH Access**: bật SSH. Việc này không bắt buộc nhưng giúp chạy migration dễ hơn nhiều.

## 2. Tải mã nguồn lên

Cấu trúc trên máy chủ (thay `ten-mien.vn` bằng tên miền của bạn):

```
/home/uXXXX/domains/ten-mien.vn/
  public_html/        ← nội dung của web/public_html
  app/                ← web/app
  bin/                ← web/bin
  migrations/         ← web/migrations
  storage/            ← tạo mới: storage/logs, storage/backups (chmod 750)
```

`index.php` tự tìm thư mục `../app`. Không đặt `app/`, `bin/`, `migrations/` hay `storage/` bên trong `public_html`.

Có thể tải lên bằng File Manager (nén zip, tải lên rồi giải nén) hoặc bằng SFTP. Thư mục `frontend/` và `tests/` không cần tải lên production.

## 3. Cấu hình

```bash
cd ~/domains/ten-mien.vn
cp app/config.sample.php app/config.php
php -r "echo bin2hex(random_bytes(32)), PHP_EOL;"   # dán kết quả vào app_key
nano app/config.php    # điền db, base_url, app_key; giữ 'secure' => true và 'rate_limit' => true
chmod 640 app/config.php
mkdir -p storage/logs storage/backups public_html/uploads/products
```

> `app_key` dùng để ký mã báo giá và tạo mã ẩn danh cho khách. **Không đổi `app_key` sau khi đã có đơn**, vì mã ẩn danh khách gửi cho Python sẽ thay đổi theo.

## 4. Tạo CSDL và tài khoản quản trị

```bash
php bin/migrate.php --status
php bin/migrate.php
php bin/seed.php                      # dữ liệu mẫu 4 nhóm hàng (bỏ qua nếu tự nhập sản phẩm)
php bin/create_admin.php chu@xuong.vn "Tên chủ xưởng" admin
```

Không có SSH: mở phpMyAdmin, nhập lần lượt `migrations/001_schema.sql` rồi `002_roles_settings.sql`. Sau đó dùng tab **Cron Jobs** chạy `create_admin.php` một lần, đặt biến `ADMIN_PASSWORD` ngay trong lệnh, rồi xóa cron đó đi.

**Không** chạy `seed.php --demo-users` hay `seed_orders.php` trên production.

## 5. Cron Jobs (hPanel → Advanced → Cron Jobs)

| Lệnh | Tần suất |
|---|---|
| `/usr/bin/php /home/uXXXX/domains/ten-mien.vn/bin/cron.php` | Mỗi 5 phút. Hủy đơn hết hạn và dọn dữ liệu tạm |
| `/usr/bin/php /home/uXXXX/domains/ten-mien.vn/bin/backup.php` | Mỗi ngày lúc 02:00. Sao lưu CSDL và ảnh |

Trang **Quản trị → Giám sát** báo đỏ nếu tác vụ hết hạn không chạy quá 30 phút, hoặc bản sao lưu cũ hơn 26 giờ.

## 6. Cấu hình nghiệp vụ trước khi mở bán

Đăng nhập `/admin`, rồi:

1. **Cấu hình**: tên cửa hàng, hotline, Zalo, email, địa chỉ, **tài khoản VietQR** (mã BIN 6 số, số tài khoản, tên chủ tài khoản không dấu) và các thời hạn giữ hàng.
2. **Vùng giao & phí**: kiểm tra danh sách tỉnh/thành và biểu phí.
3. **Sản phẩm**: thay toàn bộ thành phần, cách dùng, bảo quản và dị ứng **theo nhãn thật**. Dữ liệu mẫu chỉ để minh họa. Tải ảnh thật lên.
4. **Thông tin pháp lý và trang chính sách**: điền nhóm *Thông tin pháp lý* trong Cấu hình. Hai trang *Chính sách bảo mật thông tin* và *Điều khoản sử dụng* đã có nội dung đầy đủ và tự lấy thông tin từ Cấu hình qua biến dạng `{{hotline}}`, `{{business_name}}`… Khi sửa trong Quản trị → Trang chính sách, hãy giữ nguyên các biến này. Rà soát và chỉnh các trang giao hàng, thanh toán, đổi trả, liên hệ (còn là bản mẫu) rồi xuất bản lại. Nếu máy chủ đặt ngoài Việt Nam, đó là chuyển dữ liệu cá nhân ra nước ngoài; hộ kinh doanh và doanh nghiệp siêu nhỏ được miễn nộp hồ sơ đánh giá tác động theo Nghị định 356/2025/NĐ-CP, nhưng nên xác nhận với luật sư. Các yêu cầu pháp lý về TMĐT, thực phẩm, hóa đơn và dữ liệu cá nhân cần được xác nhận trước khi mở bán (NFR-06).
5. **Tài khoản & Phân quyền**: tạo tài khoản cho nhân viên vận hành, kho, đối soát và nội dung.
6. **Khóa API Python**: tạo 2 khóa riêng, một khóa đọc và một khóa ghi bản nháp.
7. Đặt thử một đơn COD và một đơn VietQR với số tiền nhỏ, quét mã bằng ứng dụng ngân hàng, rồi ghi nhận và đối soát trọn quy trình.
8. **Làm mới dữ liệu trước khi chạy thật**: vào Quản trị → *Làm mới dữ liệu* (chỉ Quản trị viên). Chọn phạm vi, xem trước số bản ghi sẽ xóa, rồi gõ `XOA DU LIEU THU` và nhập mật khẩu. Hệ thống tự sao lưu trước khi xóa; nếu sao lưu lỗi thì dừng, không xóa gì.
   - Muốn giữ sản phẩm mẫu làm sản phẩm thật: chỉ chọn *Đặt tồn thực tế về 0*, rồi nhập tồn đầu kỳ thật ở trang Tồn kho.
   - Muốn tự nhập sản phẩm từ đầu: chọn *Xóa sản phẩm*, *Xóa voucher và Flash Sale*, *Xóa blog và FAQ*.
   - Nên chọn thêm *Xóa tài khoản mẫu* (cần tạo tài khoản quản trị thật trước) và *Xóa nhật ký giai đoạn thử*.
   - Dùng dòng lệnh: chạy `php bin/reset_data.php --dry-run` để xem trước, rồi `php bin/reset_data.php --stock-zero --demo-users --logs`. Nếu không có SSH, chạy lệnh qua Cron Job một lần, thêm `--yes`, rồi xóa Cron Job đó.
   - Dịch vụ Python tự phát hiện dữ liệu đã làm mới và tải lại ở lần đồng bộ kế tiếp, không cần thao tác gì thêm.

## 7. Cập nhật phiên bản sau này

1. Thử trên môi trường thử nghiệm (subdomain + CSDL riêng): chạy `php bin/migrate.php`, rồi `XUONG_DB=<csdl_thu> php tests/acceptance.php`. Tên CSDL thử phải chứa chữ `test` vì script sẽ xóa và tạo lại nó.
2. Sao lưu production: `php bin/backup.php`, sau đó tải bản sao lưu về máy.
3. Tải mã mới lên rồi chạy `php bin/migrate.php`. Migration nào đã chạy thì không sửa lại; mọi thay đổi lược đồ phải đi trong migration mới (`003_…sql`).

## 8. Kiểm tra hiệu năng trên gói thật (NFR-03)

Sau khi nạp dữ liệu đại diện, đo từ máy ngoài bằng `ab`, `k6` hoặc kịch bản `web/tests/load_test.py` (xem `docs/KET-QUA-NGHIEM-THU.md`) với 20 người dùng đồng thời. Mục tiêu: p95 đọc danh mục ≤ 1 giây, p95 tạo đơn ≤ 2 giây. Khi đo tải có thể tạm đặt `'rate_limit' => false`, **nhưng phải bật lại ngay sau khi đo**.

## 9. Sửa giao diện

```bash
cd frontend && npm install
npx tailwindcss -i src/app.css -o ../public_html/assets/css/app.css --minify
```

Font Be Vietnam Pro và thư viện vẽ QR được lưu ngay trong `public_html/assets`, không phụ thuộc CDN ngoài.

## 10. Đăng nhập bằng Google / Facebook (tùy chọn)

Khách **không bắt buộc** đăng nhập — vẫn đặt hàng như cũ. Khi bật, khách đăng nhập để xem lại đơn đã đặt, được điền sẵn địa chỉ, tự bật/tắt nhận tin và tự xóa tài khoản. Chưa cấu hình thì website **không hiện nút đăng nhập**. Có thể bật một trong hai hoặc cả hai.

Thay `https://tenmien.vn` bên dưới bằng `base_url` trong `app/config.php` (phải là HTTPS khi chạy thật).

### Google

1. Vào Google Cloud Console → **Google Auth Platform** (tạo dự án mới nếu được hỏi, ví dụ "Website xưởng").
2. **Branding**: tên ứng dụng (tên xưởng), email hỗ trợ; *Trang chủ* `https://tenmien.vn`, *Chính sách quyền riêng tư* `https://tenmien.vn/chinh-sach/bao-mat`, *Điều khoản* `https://tenmien.vn/chinh-sach/dieu-khoan-su-dung`; *Miền được ủy quyền* `tenmien.vn`. Không cần tải logo (tải logo sẽ phải chờ Google xác minh thương hiệu).
3. **Audience**: chọn *External*, rồi bấm **Publish app** để chuyển sang *In production* (ở chế độ *Testing* chỉ những email được thêm làm người thử mới đăng nhập được).
4. **Data Access**: chỉ cần `openid`, `.../auth/userinfo.email`, `.../auth/userinfo.profile` (không thuộc nhóm nhạy cảm → không phải xét duyệt).
5. **Clients → Create client** → loại *Web application* → *Authorized redirect URIs*: `https://tenmien.vn/auth/google/callback` → **Create**. Chép ngay **Client ID** và **Client secret** (secret chỉ hiện một lần).

### Facebook

1. Vào developers.facebook.com → **My Apps → Create app** → chọn trường hợp sử dụng **"Authenticate and request data from users with Facebook Login"**.
2. **Use cases → Customize**: bấm **Add** ở quyền `email` (`public_profile` có sẵn). Không thêm quyền nào khác — các quyền khác phải qua App Review.
3. Trong **Facebook Login → Settings**:
   - *Valid OAuth Redirect URIs*: `https://tenmien.vn/auth/facebook/callback`
   - Bật *Enforce HTTPS* và *Use Strict Mode for redirect URIs*.
4. **App settings → Basic**:
   - *Privacy Policy URL*: `https://tenmien.vn/chinh-sach/bao-mat`
   - *Terms of Service URL*: `https://tenmien.vn/chinh-sach/dieu-khoan-su-dung`
   - *User data deletion* → chọn **Data deletion callback URL**: `https://tenmien.vn/auth/facebook/xoa-du-lieu`
   - *App icon* 1024×1024 và *Category* (Shopping).
   - Chép **App ID** và **App secret**.
5. Chuyển ứng dụng sang **Live/Published**. Nếu Meta yêu cầu xác minh doanh nghiệp (Business verification) cho tài khoản của bạn, làm theo hướng dẫn trên màn hình; trong lúc chờ, vẫn bật Google được.

### Điền vào cấu hình

Mở `app/config.php` (hPanel → File Manager), sửa mục `oauth`:

```php
'oauth' => [
    'google'   => ['client_id' => '…apps.googleusercontent.com', 'client_secret' => 'GOCSPX-…'],
    'facebook' => ['client_id' => 'App ID', 'client_secret' => 'App secret', 'graph_version' => 'v26.0'],
],
```

Nếu tệp cấu hình cài từ phiên bản cũ chưa có mục này, thêm nguyên khối trên vào trước dòng `];` cuối tệp. Lưu lại → nút **Đăng nhập** xuất hiện ở đầu trang. Không đưa `client_secret` lên GitHub hay gửi qua chat.

### Kiểm tra sau khi bật

- Đăng nhập thử bằng cả hai cách, đặt một đơn → đơn hiện ở **Tài khoản của tôi** và trong trang quản trị (dòng *Tài khoản: …*).
- Facebook: vào *Cài đặt Facebook → Ứng dụng và trang web* → gỡ website → chọn xóa hoạt động. Website ghi nhận và cấp mã tra cứu tại `/tai-khoan/trang-thai-xoa?ma=…`.

### Nguyên tắc đã cài sẵn

- Liên kết Google và Facebook vào **cùng một tài khoản chỉ khi email đã được nhà cung cấp xác minh**; khách cũng tự liên kết thêm được ở trang tài khoản.
- **Không** tự gộp đơn đặt khi chưa đăng nhập vào tài khoản theo số điện thoại (số điện thoại không được xác minh, gộp sẽ làm lộ đơn của người khác).
- Xóa tài khoản: xóa danh tính đăng nhập và thông tin giao hàng đã lưu; đơn hàng giữ lại theo nghĩa vụ kế toán nhưng bỏ liên kết.
- Website không lưu mã truy cập của Google/Facebook; lỗi nhà cung cấp chỉ ảnh hưởng nút đăng nhập, không ảnh hưởng bán hàng.
- Quản lý tài khoản khách ở **Quản trị → Tài khoản khách** (quyền *Quản lý tài khoản đăng nhập của khách*, mặc định chỉ Quản trị viên): xem cách đăng nhập đã liên kết, buộc đăng xuất mọi thiết bị, tạm khóa đăng nhập, gỡ một cách đăng nhập, xóa tài khoản khi khách yêu cầu qua hotline (hệ thống cấp mã xác nhận để gửi khách). Chỉ xóa sau khi xác minh đúng chủ tài khoản, ví dụ khách gửi email từ chính địa chỉ đăng nhập.
- Chạy thử trên máy: Google chấp nhận `http://localhost:8080/auth/google/callback`; Facebook cho phép `localhost` ở chế độ phát triển.
