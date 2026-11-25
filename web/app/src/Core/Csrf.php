<?php
declare(strict_types=1);

namespace App\Core;

/** Chống CSRF cho form quản trị và API đặt hàng (NFR-01). */
final class Csrf
{
    public static function token(): string
    {
        if (empty($_SESSION['_csrf'])) {
            $_SESSION['_csrf'] = bin2hex(random_bytes(32));
        }
        return $_SESSION['_csrf'];
    }

    public static function verify(?string $given): void
    {
        $expected = $_SESSION['_csrf'] ?? '';
        if ($expected === '' || $given === null || !hash_equals($expected, $given)) {
            throw new ApiError('CSRF_INVALID', 'Phiên làm việc đã hết hạn. Vui lòng tải lại trang và thử lại.', 419);
        }
    }

    public static function verifyRequest(): void
    {
        $given = $_POST['_csrf'] ?? ($_SERVER['HTTP_X_CSRF_TOKEN'] ?? null);
        self::verify(is_string($given) ? $given : null);
    }
}
