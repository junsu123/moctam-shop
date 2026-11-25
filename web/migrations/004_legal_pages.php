<?php
declare(strict_types=1);

// 004_legal_pages.php — tạo/cập nhật trang "Chính sách bảo mật thông tin" (/chinh-sach/bao-mat)
// và "Điều khoản sử dụng" (/chinh-sach/dieu-khoan-su-dung). Không ghi đè trang xưởng đã tự sửa.
$r = App\Domain\LegalPages::install();
echo json_encode($r, JSON_UNESCAPED_UNICODE) . ' ';
