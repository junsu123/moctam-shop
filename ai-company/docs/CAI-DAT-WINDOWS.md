# Cài đặt AI Marketing Company trên Windows 11

Dành cho máy của Owner: i5-11400F, RX 560, 16 GB RAM, Windows 11. Làm lần lượt từ trên xuống; mỗi bước có cách kiểm tra.

> Các lệnh `powershell -ExecutionPolicy Bypass -File …` chỉ cho phép chạy **đúng tệp đó, trong lần chạy đó**. Lệnh này không đổi chính sách bảo mật của máy.

## 1. Cài phần mềm nền (làm một lần)

1. **WSL2:** mở *PowerShell (Admin)*, chạy `wsl --install`, rồi khởi động lại máy.
2. **Docker Desktop:** tải tại docker.com, cài với tùy chọn *Use WSL 2 based engine*. Mở Docker Desktop và đợi biểu tượng cá voi chuyển sang trạng thái chạy. Trong *Settings → General*, bật **Start Docker Desktop when you sign in**.
3. **Git:** tải tại git-scm.com, rồi lấy mã nguồn về:
   ```powershell
   git clone https://github.com/junsu123/moctam-shop.git C:\moctam-shop
   cd C:\moctam-shop\ai-company
   ```

## 2. Kiểm tra máy

```powershell
powershell -ExecutionPolicy Bypass -File scripts\windows\kiem-tra-may.ps1
```

Script chỉ đọc thông tin và báo từng mục **[ĐẠT] / [CHƯA] / [LƯU Ý]** kèm cách sửa, gồm: Windows, RAM, ảo hóa, ổ trống, WSL2, Docker, `.wslconfig`.

## 3. Giới hạn RAM cho Docker (bắt buộc với máy 16 GB)

```powershell
powershell -ExecutionPolicy Bypass -File scripts\windows\cau-hinh-wsl.ps1
wsl --shutdown
```

Sau đó mở lại Docker Desktop. Docker sẽ dùng tối đa **6 GB RAM**, để Windows và các phần mềm khác còn khoảng 10 GB. Tệp `.wslconfig` cũ (nếu có) được sao lưu trước khi ghi đè.

## 4. Tạo tệp bí mật `.env`

```powershell
powershell -ExecutionPolicy Bypass -File scripts\windows\tao-env.ps1
```

Script tạo mật khẩu CSDL và **khóa chủ** ngẫu nhiên. **Chép tệp `.env` vào nơi an toàn** (USB riêng). Mất khóa chủ thì phải nhập lại token Telegram và khóa API trong trang quản trị. Token Telegram và khóa API Claude/OpenAI **không** để trong `.env`: anh/chị nhập chúng trong trang quản trị (từ Sprint 1), và chúng được lưu mã hóa.

## 5. Khởi động

```powershell
powershell -ExecutionPolicy Bypass -File scripts\windows\khoi-dong.ps1
```

Lần đầu mất vài phút để tải và dựng hệ thống. Xong thì trình duyệt mở **http://127.0.0.1:3000**: trang *Trung tâm điều hành* hiện 3 dòng *Máy chủ, Cơ sở dữ liệu, Hàng đợi công việc*, cả 3 có chấm xanh "Sẵn sàng".

Các container đặt `restart: unless-stopped`, nên khi bật máy và Docker Desktop tự mở thì hệ thống cũng tự chạy lại.

## 6. Để máy làm việc ổn định

- *Settings → System → Power*: khi cắm điện, đặt **Sleep = Never**.
- *Settings → Windows Update → Advanced options → Active hours*: đặt **7:00–22:00**, để Windows không tự khởi động lại trong giờ làm việc.
- Bật **BitLocker** cho ổ chứa dữ liệu (Windows 11 Pro), hoặc **Device encryption** (Windows 11 Home).
- Tài khoản Windows có mật khẩu hoặc PIN, và tự khóa màn hình khi rời máy.

## 7. Sao lưu hằng ngày

```powershell
powershell -ExecutionPolicy Bypass -File scripts\windows\sao-luu.ps1 -ThuMucNgoai "D:\OneDrive\SaoLuuAI"
```

Script giữ 14 bản trong `ai-company\backups` và chép thêm một bản ra thư mục ngoài. Đặt lịch chạy hằng ngày trong **Task Scheduler**:
1. *Create Basic Task* → *Daily*, chọn giờ.
2. *Start a program*: `powershell`.
3. Tham số: `-ExecutionPolicy Bypass -File C:\moctam-shop\ai-company\scripts\windows\sao-luu.ps1 -ThuMucNgoai "D:\OneDrive\SaoLuuAI"`.

## Khi có sự cố

| Hiện tượng | Cách xử lý |
|---|---|
| Trang không mở được | `docker compose ps` để xem dịch vụ nào không chạy; `docker compose logs --tail 50 <tên>` để xem lỗi |
| "Cơ sở dữ liệu: Chưa sẵn sàng" | Đợi 1 phút sau khi khởi động; nếu vẫn lỗi: `docker compose logs db migrate` |
| Docker báo lỗi WSL2 hoặc ảo hóa | Bật Intel VT-x trong BIOS; chạy `wsl --update` |
| Máy chậm | Kiểm tra `.wslconfig` (bước 3); đóng bớt phần mềm nặng; cân nhắc nâng 32 GB RAM |
| Cập nhật lên bản mới | `git pull` rồi chạy lại `khoi-dong.ps1` (migration tự chạy) |
