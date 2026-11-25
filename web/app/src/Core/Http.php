<?php
declare(strict_types=1);

namespace App\Core;

final class Http
{
    public static function json(array $data, int $status = 200): never
    {
        http_response_code($status);
        header('Content-Type: application/json; charset=utf-8');
        header('Cache-Control: no-store');
        echo json_enc($data);
        exit;
    }

    public static function html(string $html, int $status = 200): never
    {
        http_response_code($status);
        header('Content-Type: text/html; charset=utf-8');
        echo $html;
        exit;
    }

    public static function redirect(string $to, int $status = 303): never
    {
        header('Location: ' . $to, true, $status);
        exit;
    }

    /** @return array<string,mixed> */
    public static function body(): array
    {
        $raw = file_get_contents('php://input') ?: '';
        if ($raw === '') {
            return [];
        }
        if (strlen($raw) > 256 * 1024) {
            throw new ApiError('PAYLOAD_TOO_LARGE', 'Dữ liệu gửi lên quá lớn.', 413);
        }
        $data = json_decode($raw, true);
        if (!is_array($data)) {
            throw new ApiError('BAD_JSON', 'Dữ liệu không đúng định dạng JSON.', 400);
        }
        return $data;
    }

    public static function securityHeaders(): void
    {
        header('X-Content-Type-Options: nosniff');
        header('X-Frame-Options: SAMEORIGIN');
        header('Referrer-Policy: strict-origin-when-cross-origin');
        header("Content-Security-Policy: default-src 'self'; img-src 'self' data: https:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; frame-ancestors 'self'; base-uri 'self'; form-action 'self'");
        if (!empty($_SERVER['HTTPS']) && $_SERVER['HTTPS'] !== 'off') {
            header('Strict-Transport-Security: max-age=31536000');
        }
    }
}
