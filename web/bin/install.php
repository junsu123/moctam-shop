<?php
declare(strict_types=1);

/**
 * Cài đặt / cập nhật không tương tác — được install.sh gọi. Đọc biến môi trường:
 *   DB_HOST DB_PORT DB_NAME DB_USER DB_PASS BASE_URL STORE_NAME
 *   ADMIN_EMAIL ADMIN_PASS (chỉ khi chưa có quản trị viên)   SAMPLE=1 (nạp dữ liệu mẫu khi CSDL còn trống)
 * Lần đầu: tạo app/config.php, migration, (dữ liệu mẫu), tài khoản quản trị.
 * Lần sau: giữ config.php, chỉ chạy migration mới.
 */

$root = dirname(__DIR__);
$cfgFile = $root . '/app/config.php';
$env = fn(string $k, string $d = '') => ($v = getenv($k)) === false || $v === '' ? $d : $v;
$say = fn(string $m) => print("  • $m\n");
$fail = function (string $m): void { fwrite(STDERR, "\n  ✘ $m\n"); exit(1); };

if (PHP_VERSION_ID < 80000) $fail('Cần PHP 8.0 trở lên (đang dùng ' . PHP_VERSION . ').');
foreach (['pdo_mysql', 'mbstring', 'dom', 'json', 'openssl'] as $ext) {
    if (!extension_loaded($ext)) $fail("Thiếu extension PHP: $ext — bật trong hPanel → PHP Configuration.");
}
if (!extension_loaded('intl')) $say('Gợi ý: bật extension intl để chuẩn hóa tiếng Việt tốt hơn (không bắt buộc).');

// ---------------------------------------------------------------- cấu hình
$fresh = !is_file($cfgFile);
if ($fresh) {
    $db = ['host' => $env('DB_HOST', 'localhost'), 'port' => (int)$env('DB_PORT', '3306'), 'name' => $env('DB_NAME'), 'user' => $env('DB_USER'), 'password' => $env('DB_PASS')];
    if ($db['name'] === '' || $db['user'] === '') $fail('Thiếu DB_NAME / DB_USER.');
    try {
        new PDO("mysql:host={$db['host']};port={$db['port']};dbname={$db['name']};charset=utf8mb4", $db['user'], $db['password'], [PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION]);
    } catch (PDOException $e) {
        $fail('Không kết nối được CSDL: ' . $e->getMessage() . "\n    Kiểm tra tên CSDL, người dùng, mật khẩu trong hPanel → Databases.");
    }
    $base = rtrim($env('BASE_URL', 'https://localhost'), '/');
    $config = [
        'debug' => false,
        'base_url' => $base,
        'db' => $db,
        'app_key' => bin2hex(random_bytes(32)),
        'session' => ['name' => 'xuong_sid', 'secure' => str_starts_with($base, 'https://'), 'admin_idle_minutes' => 60],
        'paths' => ['logs' => $root . '/storage/logs', 'backups' => $root . '/storage/backups', 'uploads' => $env('UPLOADS_DIR', $root . '/public_html/uploads')],
        'trusted_proxy' => false,
        'rate_limit' => true,
    ];
    $php = "<?php\n// Tạo bởi bin/install.php lúc " . gmdate('Y-m-d H:i') . " UTC. KHÔNG đổi app_key sau khi đã có đơn.\nreturn " . var_export($config, true) . ";\n";
    file_put_contents($cfgFile, $php);
    @chmod($cfgFile, 0640);
    $say('Đã tạo app/config.php (khóa bí mật ngẫu nhiên)');
} else {
    $say('Giữ nguyên app/config.php hiện có (chế độ cập nhật)');
}
foreach (['storage/logs', 'storage/backups'] as $d) {
    if (!is_dir("$root/$d")) mkdir("$root/$d", 0750, true);
}

require $root . '/app/bootstrap.php';

use App\Core\Clock;
use App\Core\Db;
use App\Core\Settings;

$uploads = (string)config('paths.uploads');
if (!is_dir("$uploads/products")) @mkdir("$uploads/products", 0755, true);

// ---------------------------------------------------------------- migration
ob_start();
passthru(escapeshellarg(PHP_BINARY) . ' ' . escapeshellarg("$root/bin/migrate.php"), $code);
$out = trim((string)ob_get_clean());
if ($code !== 0) $fail("Migration lỗi:\n$out");
$say(str_contains($out, 'Không có migration mới') ? 'CSDL đã ở phiên bản mới nhất' : 'Đã cập nhật cấu trúc CSDL');

// ---------------------------------------------------------------- dữ liệu mẫu
if ($env('SAMPLE') === '1' && (int)Db::val('SELECT COUNT(*) FROM products') === 0) {
    passthru(escapeshellarg(PHP_BINARY) . ' ' . escapeshellarg("$root/bin/seed.php") . ' > /dev/null', $code);
    $say($code === 0 ? 'Đã nạp dữ liệu mẫu 4 nhóm hàng (xóa bằng Quản trị → Làm mới dữ liệu)' : 'Nạp dữ liệu mẫu lỗi — bỏ qua');
}

// ---------------------------------------------------------------- tên cửa hàng
if (($name = $env('STORE_NAME')) !== '') {
    Settings::set('store_name', mb_substr($name, 0, 120));
    $acc = strtoupper(preg_replace('/[^A-Za-z0-9 ]/', '', \App\Core\Text::fold($name)) ?? '');
    if (Settings::get('vietqr_account_name') === 'XUONG TRA MOC' && $acc !== '') Settings::set('vietqr_account_name', $acc);
}

// ---------------------------------------------------------------- quản trị viên
$hasAdmin = (int)Db::val("SELECT COUNT(*) FROM users WHERE role_code = 'admin' AND is_active = 1 AND email NOT LIKE '%@xuong.local'") > 0;
if (!$hasAdmin) {
    $email = mb_strtolower($env('ADMIN_EMAIL'));
    $pass = $env('ADMIN_PASS');
    if (!filter_var($email, FILTER_VALIDATE_EMAIL)) $fail('Email quản trị không hợp lệ.');
    if (strlen($pass) < 10) $fail('Mật khẩu quản trị tối thiểu 10 ký tự.');
    Db::run('INSERT INTO users (email, full_name, password_hash, role_code, created_at, updated_at) VALUES (:e, :n, :p, \'admin\', :t, :t2)
             ON DUPLICATE KEY UPDATE password_hash = VALUES(password_hash), role_code = \'admin\', is_active = 1',
        ['e' => $email, 'n' => 'Quản trị viên', 'p' => password_hash($pass, PASSWORD_DEFAULT), 't' => Clock::nowDb(), 't2' => Clock::nowDb()]);
    $say("Đã tạo tài khoản quản trị $email");
} else {
    $say('Đã có tài khoản quản trị — giữ nguyên');
}
echo "OK\n";
