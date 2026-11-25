<?php
/**
 * Sao chép thành app/config.php (KHÔNG đặt trong public_html, KHÔNG đưa vào git).
 */
return [
    'debug'    => false,
    'base_url' => 'https://ten-mien-cua-ban.vn',

    'db' => [
        'host'     => 'localhost',
        'port'     => 3306,
        'name'     => 'u123456789_xuong',
        'user'     => 'u123456789_xuong',
        'password' => 'DOI_MAT_KHAU',
    ],

    // Chuỗi bí mật ngẫu nhiên >= 32 ký tự: php -r "echo bin2hex(random_bytes(32));"
    'app_key' => 'THAY_BANG_CHUOI_NGAU_NHIEN_64_KY_TU',

    'session' => [
        'name'          => 'xuong_sid',
        'secure'        => true,   // bắt buộc HTTPS trên production
        'admin_idle_minutes' => 60,
    ],

    'paths' => [
        'logs'    => dirname(__DIR__) . '/storage/logs',
        'backups' => dirname(__DIR__) . '/storage/backups',
        'uploads' => dirname(__DIR__) . '/public_html/uploads',
    ],

    // Số proxy tin cậy (Hostinger thường đặt sau CDN) — để 0 nếu không chắc
    'trusted_proxy' => false,

    // Đăng nhập TÙY CHỌN cho khách — để trống để tắt. Hướng dẫn tạo: docs/TRIEN-KHAI-HOSTINGER.md §10
    'oauth' => [
        'google'   => ['client_id' => '', 'client_secret' => ''],
        'facebook' => ['client_id' => '', 'client_secret' => '', 'graph_version' => 'v26.0'], // client_id = App ID, client_secret = App Secret
    ],

    // Giới hạn tần suất đặt đơn/chat/đăng nhập theo IP. Chỉ đặt false khi đo tải trên môi trường thử.
    'rate_limit' => true,
];
