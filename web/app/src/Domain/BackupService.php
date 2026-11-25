<?php
declare(strict_types=1);

namespace App\Domain;

use App\Core\Clock;
use App\Core\Db;

/**
 * Sao lưu CSDL + ảnh tải lên (NFR-04). Dùng chung cho bin/backup.php và chức năng làm mới dữ liệu.
 * Ưu tiên mysqldump --single-transaction; hosting chặn exec → xuất bằng PHP thuần.
 */
final class BackupService
{
    /** @return array{file:string, bytes:int, method:string} */
    public static function run(string $label = 'xuong', int $keep = 14): array
    {
        $dir = (string)config('paths.backups', BASE_ROOT . '/storage/backups');
        if (!is_dir($dir)) mkdir($dir, 0750, true);
        $stamp = Clock::now()->format('Ymd-His') . '-' . bin2hex(random_bytes(2)); // tránh trùng tên khi 2 lần sao lưu trong cùng 1 giây
        $start = Clock::nowDb();
        $c = config('db');
        $sqlFile = "$dir/$label-$stamp.sql.gz";
        try {
            $method = 'php';
            $dump = function_exists('exec') && function_exists('shell_exec') ? trim((string)@shell_exec('command -v mysqldump || command -v mariadb-dump')) : '';
            if ($dump !== '') {
                $cnf = tempnam(sys_get_temp_dir(), 'myc');
                file_put_contents($cnf, "[client]\nuser={$c['user']}\npassword=\"{$c['password']}\"\nhost={$c['host']}\nport=" . ($c['port'] ?? 3306) . "\n");
                chmod($cnf, 0600);
                $cmd = sprintf('%s --defaults-extra-file=%s --single-transaction --routines --no-tablespaces --default-character-set=utf8mb4 %s | gzip > %s',
                    escapeshellcmd($dump), escapeshellarg($cnf), escapeshellarg($c['name']), escapeshellarg($sqlFile));
                exec($cmd, $o, $code);
                @unlink($cnf);
                if ($code !== 0 || !is_file($sqlFile) || filesize($sqlFile) < 100) {
                    throw new \RuntimeException('mysqldump lỗi mã ' . $code);
                }
                $method = 'mysqldump';
            } else {
                self::phpDump($sqlFile);
            }

            $uploads = (string)config('paths.uploads');
            if (is_dir($uploads) && class_exists(\PharData::class)) {
                $tar = "$dir/uploads-$stamp.tar";
                @unlink($tar);
                @unlink("$tar.gz");
                $p = new \PharData($tar);
                $p->buildFromDirectory($uploads);
                $p->compress(\Phar::GZ);
                unset($p);
                @unlink($tar);
            }
            foreach (["$label-*.sql.gz", 'uploads-*.tar.gz'] as $pat) {
                $all = glob("$dir/$pat") ?: [];
                rsort($all);
                foreach (array_slice($all, $keep) as $old) @unlink($old);
            }
            $res = ['file' => $sqlFile, 'bytes' => (int)filesize($sqlFile), 'method' => $method];
            Db::insert('job_runs', ['job' => 'backup', 'status' => 'ok', 'detail' => json_enc(['file' => basename($sqlFile), 'bytes' => $res['bytes']]), 'started_at' => $start, 'finished_at' => Clock::nowDb()]);
            return $res;
        } catch (\Throwable $e) {
            Db::insert('job_runs', ['job' => 'backup', 'status' => 'failed', 'detail' => mb_substr($e->getMessage(), 0, 1000), 'started_at' => $start, 'finished_at' => Clock::nowDb()]);
            throw $e;
        }
    }

    private static function phpDump(string $file): void
    {
        $gz = gzopen($file, 'wb6');
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
}
