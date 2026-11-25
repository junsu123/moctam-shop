<?php
declare(strict_types=1);

/**
 * Sao lưu CSDL + ảnh tải lên (NFR-04). Đặt Cron hằng ngày (RPO 24 giờ):
 *   /usr/bin/php .../bin/backup.php
 * Kết quả: storage/backups/xuong-YYYYmmdd-HHMMSS.sql.gz và uploads-….tar.gz, giữ 14 bản.
 * Hostinger cũng có sao lưu tự động; bản này để chủ động tải về và thử khôi phục.
 */
require __DIR__ . '/../app/bootstrap.php';

try {
    $r = App\Domain\BackupService::run();
    echo "Đã sao lưu: {$r['file']} ({$r['bytes']} byte, {$r['method']})\n";
} catch (Throwable $e) {
    fwrite(STDERR, 'Sao lưu lỗi: ' . $e->getMessage() . "\n");
    exit(1);
}
