<?php
declare(strict_types=1);

/**
 * Khởi tạo ứng dụng. Thư mục app/ nằm NGOÀI public_html (NFR-02).
 */

define('APP_ROOT', __DIR__);
define('BASE_ROOT', dirname(__DIR__));

$configFile = getenv('XUONG_CONFIG') ?: APP_ROOT . '/config.php';
if (!is_file($configFile)) {
    http_response_code(500);
    exit("Thiếu cấu hình: sao chép app/config.sample.php thành app/config.php rồi điền thông tin.\n");
}
$GLOBALS['APP_CONFIG'] = require $configFile;

date_default_timezone_set('UTC'); // lưu UTC; hiển thị Asia/Ho_Chi_Minh qua App\Core\Clock

spl_autoload_register(static function (string $class): void {
    if (strncmp($class, 'App\\', 4) !== 0) {
        return;
    }
    $file = APP_ROOT . '/src/' . str_replace('\\', '/', substr($class, 4)) . '.php';
    if (is_file($file)) {
        require $file;
    }
});

require APP_ROOT . '/src/helpers.php';
require APP_ROOT . '/src/adminhelpers.php';

$debug = (bool)config('debug', false);
error_reporting(E_ALL);
ini_set('display_errors', $debug ? '1' : '0');
ini_set('log_errors', '1');
$logDir = config('paths.logs', BASE_ROOT . '/storage/logs');
if (!is_dir($logDir)) {
    @mkdir($logDir, 0750, true);
}
ini_set('error_log', $logDir . '/php-error.log');
