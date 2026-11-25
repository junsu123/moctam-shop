<?php
declare(strict_types=1);

namespace App\Core;

final class Session
{
    public static function start(): void
    {
        if (session_status() === PHP_SESSION_ACTIVE || PHP_SAPI === 'cli') {
            if (PHP_SAPI === 'cli' && !isset($_SESSION)) {
                $_SESSION = [];
            }
            return;
        }
        session_name((string)config('session.name', 'xuong_sid'));
        session_set_cookie_params([
            'lifetime' => 0,
            'path'     => '/',
            'secure'   => (bool)config('session.secure', true),
            'httponly' => true,
            'samesite' => 'Lax',
        ]);
        ini_set('session.use_strict_mode', '1');
        ini_set('session.use_only_cookies', '1');
        session_start();
    }

    public static function id(): string
    {
        return PHP_SAPI === 'cli' ? ($_SESSION['__cli_sid'] ??= bin2hex(random_bytes(16))) : session_id();
    }

    public static function regenerate(): void
    {
        if (PHP_SAPI !== 'cli') {
            session_regenerate_id(true);
        }
    }

    public static function flash(string $type, string $msg): void
    {
        $_SESSION['_flash'][] = ['type' => $type, 'msg' => $msg];
    }

    public static function takeFlash(): array
    {
        $f = $_SESSION['_flash'] ?? [];
        unset($_SESSION['_flash']);
        return $f;
    }
}
