<?php
declare(strict_types=1);

// 006 — cập nhật Chính sách bảo mật thông tin & Điều khoản sử dụng: bổ sung đăng nhập Google/Facebook.
// Trang chưa bị xưởng sửa → xuất bản bản mới; đã sửa → thêm phiên bản chờ duyệt (không ghi đè).
$r = App\Domain\LegalPages::install();
echo json_encode($r, JSON_UNESCAPED_UNICODE) . ' ';
