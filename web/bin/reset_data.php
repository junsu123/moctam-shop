<?php
declare(strict_types=1);

/**
 * Làm mới dữ liệu trước khi chạy thật (xóa dữ liệu thử). Tự SAO LƯU trước khi xóa.
 *
 *   php bin/reset_data.php --dry-run                  # chỉ xem sẽ xóa gì
 *   php bin/reset_data.php                            # xóa đơn/khách/giao dịch thử, giữ sản phẩm
 *   php bin/reset_data.php --products --promotions --content --demo-users --logs
 *                                                     # xóa sạch dữ liệu mẫu, chỉ giữ cấu hình + danh mục + trang chính sách
 *   php bin/reset_data.php --stock-zero               # giữ sản phẩm nhưng đặt tồn về 0 để nhập tồn đầu kỳ thật
 *   thêm --yes để bỏ câu hỏi xác nhận (dùng trong Cron Job một lần khi không có SSH)
 */
require __DIR__ . '/../app/bootstrap.php';

use App\Domain\DataResetService;

$args = array_slice($argv, 1);
$opts = [];
foreach (array_keys(DataResetService::OPTIONS) as $k) {
    $opts[$k] = in_array('--' . str_replace('_', '-', $k), $args, true);
}
$opts = DataResetService::normalize($opts);
$dry = in_array('--dry-run', $args, true);
$yes = in_array('--yes', $args, true);

echo "Làm mới dữ liệu — CSDL: " . config('db.name') . "\n";
echo "Tùy chọn: " . (implode(', ', array_keys(array_filter($opts))) ?: '(chỉ dữ liệu giao dịch thử)') . "\n\nSẽ xóa / thay đổi:\n";
foreach (DataResetService::preview($opts) as $label => $n) {
    echo '  ' . $label . str_repeat(' ', max(1, 34 - mb_strlen($label))) . str_pad(number_format($n, 0, ',', '.'), 8, ' ', STR_PAD_LEFT) . "\n";
}
echo "\nGiữ nguyên: cấu hình, vai trò, tài khoản quản trị thật, danh mục, vùng giao & phí, trang chính sách.\n";
if ($dry) {
    echo "(--dry-run: chưa xóa gì)\n";
    exit(0);
}
if (!$yes) {
    echo "\nGõ chính xác \"" . DataResetService::CONFIRM_PHRASE . "\" để tiếp tục: ";
    if (trim((string)fgets(STDIN)) !== DataResetService::CONFIRM_PHRASE) {
        echo "Đã hủy.\n";
        exit(1);
    }
}
try {
    $r = DataResetService::run($opts, null, !in_array('--skip-backup', $args, true));
} catch (Throwable $e) {
    fwrite(STDERR, 'LỖI: ' . $e->getMessage() . "\n");
    exit(1);
}
echo $r['backup'] ? "Đã sao lưu trước khi xóa: {$r['backup']['file']}\n" : "Không sao lưu (--skip-backup).\n";
echo "Hoàn tất. Dịch vụ Python sẽ tự tải lại bản chụp ở lần đồng bộ tới.\n";
