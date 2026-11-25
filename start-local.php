<?php
declare(strict_types=1);

/**
 * CHẠY THỬ TRÊN MÁY TÍNH (PHP 8.0+) — một lệnh, dùng được trên Windows (XAMPP/Laragon), macOS, Linux:
 *
 *     php start-local.php
 *
 * Tự làm: kiểm tra PHP → tìm MySQL/MariaDB → tạo CSDL "moctam_local" → cấu hình → tạo bảng →
 * nạp sản phẩm mẫu, tài khoản thử, đơn mẫu → tạo khóa cho dịch vụ AI → mở http://localhost:8000
 *
 * Tùy chọn:
 *   --reset              xóa CSDL chạy thử và làm lại từ đầu
 *   --port=8001          đổi cổng
 *   --db-host=127.0.0.1 --db-port=3306 --db-user=root --db-pass=xxx   (mặc định: thử root/không mật khẩu, root/root)
 *   --no-browser         không tự mở trình duyệt
 * Dừng: Ctrl+C. Chạy lại lần sau: gõ lại đúng lệnh (dữ liệu được giữ).
 */

const DB_NAME = 'moctam_local';
$ROOT = __DIR__;
$WEB = $ROOT . '/web';
$WIN = PHP_OS_FAMILY === 'Windows';

$opt = [];
foreach (array_slice($argv, 1) as $a) {
    if (preg_match('/^--([a-z-]+)(?:=(.*))?$/', $a, $m)) $opt[$m[1]] = $m[2] ?? true;
}
function say(string $m): void { echo "  • $m\n"; }
function step(string $m): void { echo "\n▸ $m\n"; }
function fail(string $m): void { fwrite(STDERR, "\n  ✘ $m\n\n"); exit(1); }
function ask(string $q, string $def = ''): string
{
    echo "  $q" . ($def !== '' ? " [$def]" : '') . ': ';
    $a = trim((string)fgets(STDIN));
    return $a === '' ? $def : $a;
}
function run_php(array $args, bool $show = false): array
{
    $cmd = escapeshellarg(PHP_BINARY) . ' ' . implode(' ', array_map('escapeshellarg', $args)) . ' 2>&1';
    exec($cmd, $out, $code);
    if ($show) foreach ($out as $l) echo "    $l\n";
    return [$code, implode("\n", $out)];
}

echo "Chạy thử website bán hàng trên máy tính\n";

// ---------------------------------------------------------------- PHP
step('Kiểm tra PHP');
if (PHP_VERSION_ID < 80000) fail('Cần PHP 8.0 trở lên, máy đang có ' . PHP_VERSION . '. Nên dùng XAMPP/Laragon bản PHP 8.2+.');
if (PHP_VERSION_ID < 80100) say('PHP 8.0 đã hết hỗ trợ bảo mật — dùng được để chạy thử, nhưng nên nâng lên 8.2+.');
$missing = array_filter(['pdo_mysql', 'mbstring', 'dom', 'openssl'], fn($e) => !extension_loaded($e));
if ($missing) {
    fail('PHP thiếu extension: ' . implode(', ', $missing) . "\n    Mở tệp php.ini (" . (php_ini_loaded_file() ?: 'chưa có php.ini') . ")\n    bỏ dấu ; trước các dòng extension=" . implode(', extension=', $missing) . ' rồi chạy lại.');
}
say('PHP ' . PHP_VERSION . ' (' . PHP_BINARY . ')');
if (!extension_loaded('intl')) say('Gợi ý: bật extension=intl trong php.ini (không bắt buộc)');
if (!extension_loaded('fileinfo')) say('Gợi ý: bật extension=fileinfo để tải ảnh sản phẩm lên được');

// ---------------------------------------------------------------- MySQL
step('Tìm MySQL / MariaDB');
$cfgFile = "$WEB/app/config.php";
$existing = is_file($cfgFile) ? require $cfgFile : null;
$cands = [];
if (isset($opt['db-user'])) {
    $cands[] = [(string)($opt['db-host'] ?? '127.0.0.1'), (int)($opt['db-port'] ?? 3306), (string)$opt['db-user'], (string)($opt['db-pass'] ?? '')];
} elseif ($existing && ($existing['db']['name'] ?? '') === DB_NAME && empty($opt['reset'])) {
    $d = $existing['db'];
    $cands[] = [$d['host'], (int)$d['port'], $d['user'], $d['password']];
} else {
    foreach ([['root', ''], ['root', 'root']] as [$u, $p]) $cands[] = ['127.0.0.1', (int)($opt['db-port'] ?? 3306), $u, $p];
}
$pdo = null;
$conn = null;
for ($try = 0; $try < 4 && !$pdo; $try++) {
    foreach ($cands as $c) {
        try {
            $pdo = new PDO("mysql:host={$c[0]};port={$c[1]};charset=utf8mb4", $c[2], $c[3], [PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION, PDO::ATTR_TIMEOUT => 3]);
            $conn = $c;
            break;
        } catch (PDOException $e) {
            $last = $e->getMessage();
        }
    }
    if (!$pdo) {
        if ($try === 0) {
            echo "  Chưa kết nối được (" . preg_replace('/^SQLSTATE\[\w+\] \[\d+\] /', '', $last) . ").\n";
            echo "  Hãy bật MySQL (XAMPP: bấm Start ở dòng MySQL; Laragon: Start All) rồi nhập thông tin:\n";
        } else {
            echo "  Vẫn chưa được: " . preg_replace('/^SQLSTATE\[\w+\] \[\d+\] /', '', $last) . "\n";
        }
        if ($try === 3) break;
        $cands = [[ask('Máy chủ', '127.0.0.1'), (int)ask('Cổng', '3306'), ask('Người dùng', 'root'), ask('Mật khẩu (để trống nếu không có)')]];
    }
}
if (!$pdo) fail('Không kết nối được MySQL. Kiểm tra MySQL đã chạy và thông tin đăng nhập.');
say("Kết nối {$conn[2]}@{$conn[0]}:{$conn[1]} — " . $pdo->query('SELECT VERSION()')->fetchColumn());

if (!empty($opt['reset'])) {
    $pdo->exec('DROP DATABASE IF EXISTS `' . DB_NAME . '`');
    @unlink($cfgFile);
    @unlink("$ROOT/ai/config.toml");
    foreach (glob("$ROOT/ai/data/*") ?: [] as $f) @unlink($f);
    say('Đã xóa dữ liệu chạy thử cũ (--reset)');
}
$pdo->exec('CREATE DATABASE IF NOT EXISTS `' . DB_NAME . '` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci');
say('CSDL: ' . DB_NAME);

// ---------------------------------------------------------------- cấu hình
$port = (int)($opt['port'] ?? 8000);
for ($p = $port; $p < $port + 20; $p++) {
    $s = @fsockopen('127.0.0.1', $p, $en, $es, 0.2);
    if (!$s) { $port = $p; break; }
    fclose($s);
}
$base = "http://localhost:$port";
step('Cấu hình');
$config = [
    'debug' => true,
    'base_url' => $base,
    'db' => ['host' => $conn[0], 'port' => $conn[1], 'name' => DB_NAME, 'user' => $conn[2], 'password' => $conn[3]],
    'app_key' => $existing['app_key'] ?? bin2hex(random_bytes(32)),
    'session' => ['name' => 'moctam_local', 'secure' => false, 'admin_idle_minutes' => 480],
    'paths' => ['logs' => "$WEB/storage/logs", 'backups' => "$WEB/storage/backups", 'uploads' => "$WEB/public_html/uploads"],
    'trusted_proxy' => false,
    'rate_limit' => true,
    // Đăng nhập Google/Facebook: điền để thử (Google cho phép http://localhost làm địa chỉ chuyển hướng)
    'oauth' => $existing['oauth'] ?? ['google' => ['client_id' => '', 'client_secret' => ''], 'facebook' => ['client_id' => '', 'client_secret' => '', 'graph_version' => 'v26.0']],
];
file_put_contents($cfgFile, "<?php\n// Cấu hình CHẠY THỬ trên máy (tạo bởi start-local.php). Không dùng cho Hostinger.\nreturn " . var_export($config, true) . ";\n");
foreach (["$WEB/storage/logs", "$WEB/storage/backups", "$WEB/public_html/uploads/products"] as $d) if (!is_dir($d)) mkdir($d, 0775, true);
say('web/app/config.php (chế độ chạy thử, http)');

// ---------------------------------------------------------------- bảng + dữ liệu
step('Tạo bảng và dữ liệu mẫu');
[$code, $out] = run_php(["$WEB/bin/migrate.php"]);
if ($code !== 0) fail("Tạo bảng lỗi:\n$out");
say(str_contains($out, 'Không có migration mới') ? 'Bảng đã có sẵn' : 'Đã tạo bảng');
$db = new PDO('mysql:host=' . $conn[0] . ';port=' . $conn[1] . ';dbname=' . DB_NAME . ';charset=utf8mb4', $conn[2], $conn[3]);
if ((int)$db->query('SELECT COUNT(*) FROM products')->fetchColumn() === 0) {
    [$code, $out] = run_php(["$WEB/bin/seed.php", '--demo-users']);
    if ($code !== 0) fail("Nạp dữ liệu mẫu lỗi:\n$out");
    say('16 sản phẩm mẫu, 4 vùng giao, voucher, Flash Sale, FAQ, blog, 5 tài khoản thử');
    echo "  • Đang tạo đơn mẫu 90 ngày qua (để thử dịch vụ AI)…\n";
    [$code, $out] = run_php(["$WEB/bin/seed_orders.php", '20']);
    say($code === 0 ? trim($out) : 'Bỏ qua đơn mẫu: ' . mb_substr($out, 0, 200));
} else {
    say('Giữ dữ liệu đã có (thêm --reset để làm lại từ đầu)');
}

// ---------------------------------------------------------------- dịch vụ AI
$aiCfg = "$ROOT/ai/config.toml";
if (is_dir("$ROOT/ai") && !is_file($aiCfg)) {
    $mk = function (string $name, string $scopes) use ($db): string {
        $key = 'xk_' . bin2hex(random_bytes(24));
        $st = $db->prepare('INSERT INTO api_keys (name, key_prefix, key_hash, scopes, created_at) VALUES (?,?,?,?,UTC_TIMESTAMP())');
        $st->execute([$name, substr($key, 0, 8), hash('sha256', $key), $scopes]);
        return $key;
    };
    $r = $mk('may-tinh-doc', 'events:read,catalog:read');
    $w = $mk('may-tinh-ghi', 'drafts:write');
    file_put_contents($aiCfg, "# Tạo bởi start-local.php — chạy thử dịch vụ AI với website trên máy\ndb_path = \"data/xuong_ai.sqlite3\"\nproposals_dir = \"proposals\"\n\n[site]\nbase_url = \"$base\"\nread_key = \"$r\"\nwrite_key = \"$w\"\n\n[llm]\nprovider = \"none\"   # đổi thành anthropic/openai + api_key để thử soạn nháp blog/FAQ\napi_key = \"\"\n");
    say('Đã tạo ai/config.toml + 2 khóa API cho dịch vụ AI');
} elseif (is_file($aiCfg)) {
    $c = file_get_contents($aiCfg);
    file_put_contents($aiCfg, preg_replace('#base_url = "http://localhost:\d+"#', "base_url = \"$base\"", $c));
}

// ---------------------------------------------------------------- chạy
$router = "$WEB/tests/devrouter.php";
echo "\n✔ Sẵn sàng.\n";
echo "  Cửa hàng:   $base\n";
echo "  Quản trị:   $base/admin\n";
echo "  Tài khoản:  admin@xuong.local   (mật khẩu Demo@12345)\n";
echo "              vanhanh@ · kho@ · doisoat@ · noidung@xuong.local — cùng mật khẩu, để thử phân quyền\n";
echo "  Thử AI:     mở cửa sổ lệnh khác →  cd ai  →  python -m xuong_ai once sync\n";
echo "  Dừng:       Ctrl+C\n\n";

if (empty($opt['no-browser'])) {
    $open = $WIN ? 'start "" ' . escapeshellarg($base) : (PHP_OS_FAMILY === 'Darwin' ? 'open ' . escapeshellarg($base) : 'xdg-open ' . escapeshellarg($base) . ' >/dev/null 2>&1');
    @pclose(@popen($WIN ? "cmd /c $open" : "(sleep 1; $open) &", 'r'));
}
if (!$WIN) putenv('PHP_CLI_SERVER_WORKERS=4');
passthru(escapeshellarg(PHP_BINARY) . ' -S ' . escapeshellarg("localhost:$port") . ' -t ' . escapeshellarg("$WEB/public_html") . ' ' . escapeshellarg($router));
