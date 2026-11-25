# Sao lưu và khôi phục

Mục tiêu đề xuất (NFR-04): **mất tối đa 24 giờ dữ liệu** (RPO) và **khôi phục trong 8 giờ** (RTO).

## Sao lưu

| Lớp | Cách làm | Tần suất |
|---|---|---|
| CSDL + ảnh tải lên | `bin/backup.php` tạo `storage/backups/xuong-YYYYmmdd-HHMM.sql.gz` và `uploads-YYYYmmdd.tar.gz`, giữ 14 bản gần nhất | Cron hằng ngày lúc 02:00 |
| Bản sao ngoài máy chủ | Tải 2 tệp mới nhất về máy hoặc Google Drive | Hằng tuần, và trước mỗi lần cập nhật |
| Sao lưu của Hostinger | hPanel → Files → Backups (tùy gói, thường giữ theo tuần/ngày) | Tự động |
| Python cục bộ | Sao chép `ai/data/xuong_ai.sqlite3`. Có thể bỏ qua: nếu mất, chạy `python -m xuong_ai snapshot` để tạo lại từ website | Không bắt buộc |

`backup.php` dùng `mysqldump --single-transaction`, nên sao lưu được khi web vẫn đang bán. Nếu gói hosting chặn `exec`, script tự chuyển sang xuất bằng PHP thuần. Tuổi của bản sao lưu gần nhất hiển thị ở **Quản trị → Giám sát**.

## Khôi phục

1. Tạo CSDL trống (hoặc CSDL thử nghiệm để diễn tập).
2. Nhập dữ liệu:
   ```bash
   gunzip -c storage/backups/xuong-20261125-0200.sql.gz | mysql -h localhost -u USER -p TEN_CSDL
   ```
   Nếu không có SSH: giải nén tệp `.sql.gz` rồi dùng phpMyAdmin → Import. Với tệp lớn, chia nhỏ hoặc nhờ hỗ trợ Hostinger.
3. Khôi phục ảnh:
   ```bash
   tar -xzf storage/backups/uploads-20261125.tar.gz -C public_html/uploads
   ```
4. Kiểm tra `app/config.php` trỏ đúng CSDL, **dùng lại đúng `app_key` cũ**, rồi chạy `php bin/migrate.php --status`.
5. Kiểm tra trên web: danh mục, ảnh sản phẩm, một vài đơn gần nhất, tồn kho, khoản thu và lịch sử trạng thái.
6. Chạy `php bin/cron.php` một lần, rồi xem trang Giám sát.
7. Python: chạy `python -m xuong_ai snapshot`. Con trỏ sẽ được đặt lại theo `as_of_seq` của bản khôi phục.

## Diễn tập

Ca nghiệm thu **AT-11** (`tests/acceptance.php`) tự động sao lưu, khôi phục sang CSDL `<tên>_restore`, rồi so khớp số sản phẩm, ảnh, đơn, tổng tồn, khoản thu và lịch sử trạng thái. Lần chạy gần nhất: khớp 100% trong 0,6 giây với dữ liệu thử. Nên diễn tập thủ công theo các bước trên mỗi quý, và ghi lại thời gian thực tế để đối chiếu với RTO 8 giờ.
