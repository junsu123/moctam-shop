<?php
declare(strict_types=1);

/** Tạo tài khoản quản trị đầu tiên: php bin/create_admin.php email@xuong.vn "Họ tên" [role] */
require __DIR__ . '/../app/bootstrap.php';

use App\Core\Clock;
use App\Core\Db;

[$_, $email, $name, $role] = $argv + [null, null, null, 'admin'];
if (!$email || !$name) {
    fwrite(STDERR, "Cách dùng: php bin/create_admin.php email \"Họ tên\" [admin|operations|warehouse|reconciliation|content]\n");
    exit(1);
}
$pass = getenv('ADMIN_PASSWORD') ?: '';
if ($pass === '') {
    echo 'Mật khẩu (>= 10 ký tự): ';
    system('stty -echo 2>/dev/null');
    $pass = trim((string)fgets(STDIN));
    system('stty echo 2>/dev/null');
    echo "\n";
}
if (strlen($pass) < 10) {
    fwrite(STDERR, "Mật khẩu tối thiểu 10 ký tự.\n");
    exit(1);
}
Db::insert('users', [
    'email' => mb_strtolower($email), 'full_name' => $name, 'password_hash' => password_hash($pass, PASSWORD_DEFAULT),
    'role_code' => $role, 'created_at' => Clock::nowDb(), 'updated_at' => Clock::nowDb(),
]);
echo "Đã tạo tài khoản $email (vai trò $role).\n";
