<?php
declare(strict_types=1);

/**
 * Sao lưu CSDL + ảnh tải lên (NFR-04). Đặt Cron hằng ngày (RPO 24 giờ):
 *   /usr/bin/php .../bin/backup.php
 * Kết quả: storage/backups/xuong-YYYYmmdd-HHMM.sql.gz và uploads-YYYYmmdd.tar.gz, giữ 14 bản.
 * Hostinger cũng có sao lưu tự động; bản này để chủ động tải về và thử khôi phục.
 */
require __DIR__ . '/../app/bootstrap.php';

use App\Core\Clock;
use App\Core\Db;

$dir = (string)config('paths.backups', BASE_ROOT . '/storage/backups');
if (!is_dir($dir)) mkdir($dir, 0750, true);
$stamp = Clock::now()->format('Ymd-Hi');
$start = Clock::nowDb();
$c = config('db');

try {
    $sqlFile = "$dir/xuong-$stamp.sql.gz";
    $cnf = tempnam(sys_get_temp_dir(), 'myc');
    file_put_contents($cnf, "[client]\nuser={$c['user']}\npassword=\"{$c['password']}\"\nhost={$c['host']}\nport=" . ($c['port'] ?? 3306) . "\n");
    chmod($cnf, 0600);
    $dump = trim((string)shell_exec('command -v mysqldump || command -v mariadb-dump'));
    if ($dump !== '') {
        $cmd = sprintf('%s --defaults-extra-file=%s --single-transaction --routines --no-tablespaces --default-character-set=utf8mb4 %s | gzip > %s',
            escapeshellcmd($dump), escapeshellarg($cnf), escapeshellarg($c['name']), escapeshellarg($sqlFile));
        exec($cmd, $o, $code);
        if ($code !== 0) throw new RuntimeException('mysqldump lỗi mã ' . $code);
    } else {
        // Dự phòng thuần PHP khi hosting không cho exec
        $gz = gzopen($sqlFile, 'wb6');
        gzwrite($gz, "SET NAMES utf8mb4;\nSET FOREIGN_KEY_CHECKS=0;\n");
        foreach (Db::all('SHOW TABLES') as $t) {
            $table = array_values($t)[0];
            $create = Db::one("SHOW CREATE TABLE `$table`");
            gzwrite($gz, "DROP TABLE IF EXISTS `$table`;\n" . $create['Create Table'] . ";\n");
            $st = Db::run("SELECT * FROM `$table`");
            while ($row = $st->fetch()) {
                $vals = array_map(fn($v) => $v === null ? 'NULL' : Db::pdo()->quote((string)$v), $row);
                gzwrite($gz, "INSERT INTO `$table` VALUES (" . implode(',', $vals) . ");\n");
            }
        }
        gzwrite($gz, "SET FOREIGN_KEY_CHECKS=1;\n");
        gzclose($gz);
    }
    @unlink($cnf);

    $uploads = (string)config('paths.uploads');
    $imgFile = "$dir/uploads-" . Clock::now()->format('Ymd') . '.tar.gz';
    if (is_dir($uploads) && class_exists(PharData::class)) {
        $tar = substr($imgFile, 0, -3);
        @unlink($tar);
        @unlink($imgFile);
        $p = new PharData($tar);
        $p->buildFromDirectory($uploads);
        $p->compress(Phar::GZ);
        @unlink($tar);
    }

    // Giữ 14 bản gần nhất
    foreach (['xuong-*.sql.gz', 'uploads-*.tar.gz'] as $pat) {
        $all = glob("$dir/$pat") ?: [];
        rsort($all);
        foreach (array_slice($all, 14) as $old) @unlink($old);
    }
    $size = filesize($sqlFile);
    Db::insert('job_runs', ['job' => 'backup', 'status' => 'ok', 'detail' => json_enc(['file' => basename($sqlFile), 'bytes' => $size]), 'started_at' => $start, 'finished_at' => Clock::nowDb()]);
    echo "Đã sao lưu: $sqlFile ($size byte)\n";
} catch (Throwable $e) {
    Db::insert('job_runs', ['job' => 'backup', 'status' => 'failed', 'detail' => $e->getMessage(), 'started_at' => $start, 'finished_at' => Clock::nowDb()]);
    fwrite(STDERR, 'Sao lưu lỗi: ' . $e->getMessage() . "\n");
    exit(1);
}
