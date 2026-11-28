<?php
declare(strict_types=1);

/**
 * Tạo khóa API cho dịch vụ Python. Khóa chỉ hiện MỘT lần; CSDL chỉ lưu SHA-256.
 *   php bin/create_api_key.php "python-doc" events:read,catalog:read
 *   php bin/create_api_key.php "python-ghi" drafts:write
 */
require __DIR__ . '/../app/bootstrap.php';

use App\Core\Clock;
use App\Core\Db;

[$_, $name, $scopes] = $argv + [null, null, null];
$allowed = ['events:read', 'catalog:read', 'drafts:write', 'content:publish'];
$list = array_filter(array_map('trim', explode(',', (string)$scopes)));
if (!$name || !$list || array_diff($list, $allowed)) {
    fwrite(STDERR, "Cách dùng: php bin/create_api_key.php <tên> <" . implode('|', $allowed) . ",...>\n");
    exit(1);
}
$key = 'xk_' . bin2hex(random_bytes(24));
Db::insert('api_keys', [
    'name' => $name, 'key_prefix' => substr($key, 0, 8), 'key_hash' => hash('sha256', $key),
    'scopes' => implode(',', $list), 'created_at' => Clock::nowDb(),
]);
echo "Khóa API ($name, " . implode(',', $list) . "):\n$key\nLưu vào cấu hình Python ngay — khóa sẽ không hiển thị lại.\n";
