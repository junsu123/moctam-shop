<?php
declare(strict_types=1);

use App\Core\Clock;
use App\Core\Csrf;
use App\Core\Settings;

function config(string $key, mixed $default = null): mixed
{
    $value = $GLOBALS['APP_CONFIG'] ?? [];
    foreach (explode('.', $key) as $part) {
        if (!is_array($value) || !array_key_exists($part, $value)) {
            return $default;
        }
        $value = $value[$part];
    }
    return $value;
}

/** Mã hóa đầu ra HTML (NFR-01). */
function e(mixed $value): string
{
    return htmlspecialchars((string)$value, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8');
}

function money(int|string|null $vnd): string
{
    return number_format((int)$vnd, 0, ',', '.') . ' ₫';
}

function setting(string $key, string $default = ''): string
{
    return Settings::get($key, $default);
}

/** Hiển thị mốc UTC theo giờ Việt Nam. */
function vn_time(?string $utc, string $format = 'd/m/Y H:i'): string
{
    return $utc ? Clock::toLocal($utc)->format($format) : '';
}

function csrf_field(): string
{
    return '<input type="hidden" name="_csrf" value="' . e(Csrf::token()) . '">';
}

function url(string $path = '/', array $query = []): string
{
    $q = $query ? ('?' . http_build_query($query)) : '';
    return $path . $q;
}

/** Địa chỉ một cấp của danh mục / sản phẩm / bài viết / trang: /{slug}.html */
function page_url(string $slug): string
{
    return \App\Domain\Urls::to($slug);
}

/** Trang cố định: cart, checkout, search, flash, blog, faq, account, login, deletion */
function fixed_url(string $key, array $query = []): string
{
    return \App\Domain\Urls::fixed($key, $query);
}

function asset(string $path): string
{
    $file = BASE_ROOT . '/public_html/assets/' . ltrim($path, '/');
    $v = is_file($file) ? substr((string)filemtime($file), -6) : '1';
    return '/assets/' . ltrim($path, '/') . '?v=' . $v;
}

function old(array $src, string $key, string $default = ''): string
{
    return e($src[$key] ?? $default);
}

function client_ip(): string
{
    if (config('trusted_proxy') && !empty($_SERVER['HTTP_X_FORWARDED_FOR'])) {
        return trim(explode(',', (string)$_SERVER['HTTP_X_FORWARDED_FOR'])[0]);
    }
    return (string)($_SERVER['REMOTE_ADDR'] ?? '0.0.0.0');
}

function json_enc(mixed $v): string
{
    return json_encode($v, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES | JSON_THROW_ON_ERROR);
}

function json_dec(?string $s, mixed $default = []): mixed
{
    if ($s === null || $s === '') {
        return $default;
    }
    $v = json_decode($s, true);
    return $v === null ? $default : $v;
}
