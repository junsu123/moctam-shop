<?php
declare(strict_types=1);

// 008 — Điều khoản sử dụng: bổ sung việc xưởng có thể đăng xuất / tạm khóa đăng nhập và xóa tài khoản thay khách.
// Trang chưa bị xưởng sửa → xuất bản bản mới; đã sửa → thêm phiên bản chờ duyệt (không ghi đè).
$r = App\Domain\LegalPages::install();
echo json_encode($r, JSON_UNESCAPED_UNICODE) . ' ';
