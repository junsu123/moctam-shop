<?php
declare(strict_types=1);

/**
 * Áp dụng migration theo phiên bản.
 *   php bin/migrate.php            — áp dụng các migration chưa chạy
 *   php bin/migrate.php --status   — xem trạng thái
 *   php bin/migrate.php --dry-run  — liệt kê sẽ chạy gì
 * Quy trình: chạy trên môi trường thử nghiệm → sao lưu production (bin/backup.php) → chạy production.
 */
require __DIR__ . '/../app/bootstrap.php';

use App\Core\Db;

$dir = BASE_ROOT . '/migrations';
$files = glob($dir . '/*.sql') ?: [];
sort($files);

Db::pdo()->exec("CREATE TABLE IF NOT EXISTS schema_migrations (version VARCHAR(64) NOT NULL PRIMARY KEY, applied_at DATETIME NOT NULL, checksum CHAR(64) NOT NULL) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4");
$applied = [];
foreach (Db::all('SELECT version, checksum FROM schema_migrations') as $r) {
    $applied[$r['version']] = $r['checksum'];
}

$status = in_array('--status', $argv, true);
$dry = in_array('--dry-run', $argv, true);
$pending = 0;
foreach ($files as $f) {
    $ver = basename($f, '.sql');
    $sum = hash_file('sha256', $f);
    if (isset($applied[$ver])) {
        if ($applied[$ver] !== $sum) {
            fwrite(STDERR, "CẢNH BÁO: $ver đã chạy nhưng nội dung tệp đã thay đổi. Hãy tạo migration mới thay vì sửa tệp cũ.\n");
        }
        if ($status) echo "  [đã chạy] $ver\n";
        continue;
    }
    $pending++;
    if ($status || $dry) {
        echo "  [chờ]     $ver\n";
        continue;
    }
    echo "→ Áp dụng $ver ... ";
    $sql = file_get_contents($f);
    $sql = preg_replace('/^\s*--.*$/m', '', $sql);
    foreach (array_filter(array_map('trim', preg_split('/;\s*$/m', $sql))) as $stmt) {
        if (stripos($stmt, 'CREATE TABLE IF NOT EXISTS schema_migrations') !== false) continue;
        Db::pdo()->exec($stmt);
    }
    Db::run('INSERT INTO schema_migrations (version, applied_at, checksum) VALUES (:v, UTC_TIMESTAMP(), :c)', ['v' => $ver, 'c' => $sum]);
    echo "xong\n";
}
echo $pending === 0 ? "Không có migration mới.\n" : ($status || $dry ? "$pending migration đang chờ.\n" : "Hoàn tất.\n");
