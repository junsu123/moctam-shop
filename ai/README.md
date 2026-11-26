# Dịch vụ AI cục bộ (giai đoạn 2)

Chạy trên máy tính của xưởng (Windows, macOS hoặc Linux). Cần **Python 3.11 trở lên** và **không cần cài thêm gói nào**; chỉ riêng việc chạy kiểm thử cần `pytest`. Website vẫn bán hàng bình thường khi máy này tắt.

## Cài đặt

```bash
cd ai
cp config.example.toml config.toml      # điền base_url, read_key, write_key
python -m xuong_ai once sync            # lần đầu: tải bản chụp toàn bộ đơn
python -m xuong_ai once catalog         # nạp sản phẩm, FAQ đã duyệt vào bộ nhớ
python -m xuong_ai status
```

Khóa API lấy ở Quản trị → **Khóa API Python**. Tạo 2 khóa: một khóa đọc (`events:read`, `catalog:read`) và một khóa ghi bản nháp (`drafts:write`).

LLM là tùy chọn. Đặt `provider = "none"` thì các tác nhân không cần LLM (đồng bộ, mua kèm, chăm sóc lại, bảo trì) vẫn chạy bình thường. Khi bật LLM, kiểm tra tên model và bảng giá hiện hành của nhà cung cấp, rồi điền `price_in_per_mtok` / `price_out_per_mtok` để ước tính chi phí cho đúng.

## Văn phòng AI và bộ não "Trưởng văn phòng"

Dịch vụ này là một **văn phòng AI** gồm 6 nhân viên (thư ký dữ liệu, tư vấn viên, biên tập SEO, chăm sóc khách, phân tích bán hàng, kỹ thuật bảo trì) và một **bộ não** điều phối. Mỗi phút bộ não làm một vòng:

1. **Cảm nhận**: đọc dữ liệu cục bộ thành tín hiệu. Ví dụ: câu hỏi khách chưa có câu trả lời, sản phẩm thiếu bài viết, khách đến kỳ mua lại, đơn tụt bất thường, website không phản hồi.
2. **Cân nhắc**: chấm điểm theo mục tiêu, rồi đối chiếu nội quy: hạn mức LLM, sức duyệt của nhân viên, loại câu hỏi chỉ người được trả lời, công tắc tạm dừng.
3. **Giao việc** cho nhân viên. Việc AI không được làm được chuyển cho chủ xưởng.
4. **Học** từ kết quả duyệt trên website: bản nào được duyệt, bị sửa hay bị từ chối, và góp ý của người duyệt. Góp ý được đưa vào lần soạn sau.
5. **Báo cáo**: mỗi sáng ghi `office/<ngày>-ban-tin-van-phong.md`.

Chi tiết ở `docs/VAN-PHONG-AI.md`. Các tham số nằm trong mục `[brain]` của `config.toml`.

```bash
python -m xuong_ai think         # bộ não đang nghĩ gì: tín hiệu, việc cần người, quyết định + lý do (không làm, không ghi)
python -m xuong_ai tick          # làm đúng một nhịp
python -m xuong_ai office        # nhân sự, độ tin cậy đã học, việc cần chủ xưởng
python -m xuong_ai brief         # viết bản tin văn phòng ngay
```

**Tạm dừng văn phòng**: tạo tệp `STOP` trong thư mục `ai` (hoặc đặt `paused = true`). Xóa tệp để làm việc lại.

## Chạy nền

```bash
python -m xuong_ai run           # văn phòng làm việc nền: bộ não quyết định việc gì, lúc nào, ai làm; chạy bù khi bật máy
python -m xuong_ai run --legacy  # (dự phòng) bộ hẹn giờ cũ: chạy mọi tác nhân theo lịch cố định
```

- **Windows**: Task Scheduler → Create Task → Trigger "At log on" → Action: `pythonw.exe -m xuong_ai run`, Start in: thư mục `ai`.
- **macOS**: tạo LaunchAgent (`~/Library/LaunchAgents/vn.xuong.ai.plist`) chạy `python3 -m xuong_ai run`, đặt `WorkingDirectory` là thư mục `ai`.
- **Linux**: tạo user service systemd hoặc dùng `@reboot` trong crontab.

## Các lệnh

| Lệnh | Việc làm |
|---|---|
| `run` / `think` / `tick` / `office` / `brief` | Văn phòng AI (xem phần trên) |
| `once sync` | Kéo sự kiện đơn (con trỏ chỉ dời sau khi ghi xong cả lô) |
| `once feedback` | Lấy kết quả duyệt bản nháp AI và số bản đang chờ duyệt |
| `once catalog` | Nạp danh mục, FAQ đã duyệt, câu hỏi chat chưa có câu trả lời |
| `once crosssell` | Đề xuất sản phẩm mua kèm từ các đơn đã giao |
| `once care` | Danh sách khách đến kỳ mua lại (chỉ khách đã đồng ý nhận tiếp thị) |
| `once faq_drafts` | Soạn FAQ cho câu hỏi chưa có câu trả lời; bộ nhớ đã có thì không gọi LLM |
| `once blog_drafts` | Soạn bài blog từ thông tin sản phẩm đã duyệt |
| `once maintenance` | Viết `proposals/<ngày>-de-xuat-bao-tri.md`: chi phí LLM, tỷ lệ dùng lại bộ nhớ, ngưỡng đề xuất, ca kiểm thử |
| `calibrate [eval.jsonl]` | Hiệu chỉnh ngưỡng khớp FAQ trên tập câu hỏi tiếng Việt |
| `snapshot` | Tải lại toàn bộ bản chụp (sau khi khôi phục CSDL website) |

Các lệnh `once …` chạy thẳng một tác nhân, không qua bộ não. Lệnh này dùng để thử hoặc chạy tay. Mọi bản nháp, gợi ý và danh sách đều vào trạng thái **chờ duyệt** trên website. Nhân viên xem và duyệt ở các mục: Blog/FAQ, Gợi ý mua kèm, Chăm sóc lại.

## Hiệu chỉnh ngưỡng chat

Mỗi khi thêm hoặc sửa FAQ, cập nhật `eval/faq_eval.jsonl` theo dạng: mỗi dòng gồm câu hỏi và tiêu đề FAQ đúng, hoặc `null` nếu phải chuyển sang kênh hỗ trợ. Sau đó chạy:

```bash
python -m xuong_ai once catalog && python -m xuong_ai calibrate
```

Lấy ngưỡng đề xuất, đặt vào Quản trị → Cấu hình → *Ngưỡng khớp FAQ của chat*. Website và Python dùng cùng một thuật toán BM25, nên ngưỡng này áp dụng chính xác cho chat trên website.

## Kiểm thử

```bash
pip install pytest && python -m pytest -v
```

## Dữ liệu và quyền riêng tư

- CSDL cục bộ (`data/xuong_ai.sqlite3`, kể cả sổ sách của bộ não) **không có** tên, số điện thoại hay địa chỉ khách. Khách chỉ được nhận diện bằng `customer_key`, là mã băm do website tạo.
- Trước khi gửi bất kỳ nội dung nào cho LLM, số điện thoại và email đều được che.
- Không đưa `config.toml` vào git hay chia sẻ cho người khác. Nếu mất máy, vào trang quản trị thu hồi ngay hai khóa API.
