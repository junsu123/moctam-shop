<?php
declare(strict_types=1);

namespace App\Http\Admin;

use App\Core\ApiError;
use App\Core\Auth;
use App\Core\Csrf;
use App\Core\Http;
use App\Core\Session;
use App\Core\View;

abstract class Base
{
    public function __construct()
    {
        $path = parse_url($_SERVER['REQUEST_URI'] ?? '/', PHP_URL_PATH);
        if ($path !== '/admin/login' && !Auth::user()) {
            if (($_SERVER['REQUEST_METHOD'] ?? 'GET') === 'GET') {
                $_SESSION['after_login'] = $_SERVER['REQUEST_URI'] ?? '/admin';
            }
            Http::redirect('/admin/login');
        }
        header('Cache-Control: no-store');
        header('X-Robots-Tag: noindex');
        if (($_SERVER['REQUEST_METHOD'] ?? 'GET') === 'POST') {
            Csrf::verifyRequest();
        }
    }

    protected function view(string $tpl, array $data = []): string
    {
        $data['errors'] = $_SESSION['_errors'] ?? [];
        $data['old'] = $_SESSION['_old'] ?? [];
        unset($_SESSION['_errors'], $_SESSION['_old']);
        $data['flash'] = Session::takeFlash();
        $data['me'] = Auth::user();
        return View::render('admin/' . $tpl, $data, 'admin/layout');
    }

    protected function back(string $msg = 'Đã lưu.', string $to = ''): void
    {
        Session::flash('ok', $msg);
        Http::redirect($to ?: self::referer());
    }

    protected function need(string $perm): void
    {
        Auth::require($perm);
    }

    protected static function referer(): string
    {
        $ref = (string)($_SERVER['HTTP_REFERER'] ?? '');
        $path = parse_url($ref, PHP_URL_PATH) ?: '/admin';
        $q = parse_url($ref, PHP_URL_QUERY);
        return str_starts_with($path, '/admin') ? $path . ($q ? '?' . $q : '') : '/admin';
    }

    public static function handleError(ApiError $e, string $method): void
    {
        if ($e->status === 401) {
            Http::redirect('/admin/login');
        }
        if ($method === 'POST') {
            $_SESSION['_errors'] = array_filter($e->data['fields'] ?? []);
            $_SESSION['_old'] = $_POST;
            unset($_SESSION['_old']['_csrf'], $_SESSION['_old']['password']);
            Session::flash('error', $e->getMessage());
            Http::redirect(self::referer());
        }
        Http::html(View::render('admin/error', ['title' => 'Không thực hiện được', 'code' => $e->status, 'message' => $e->getMessage(), 'me' => Auth::user(), 'flash' => [], 'errors' => [], 'old' => []], 'admin/layout'), $e->status);
    }

    protected function int(string $key, int $default = 0): int
    {
        return (int)($_POST[$key] ?? $_GET[$key] ?? $default);
    }

    protected function str(string $key, string $default = ''): string
    {
        $v = $_POST[$key] ?? $_GET[$key] ?? $default;
        return is_string($v) ? trim($v) : $default;
    }
}
