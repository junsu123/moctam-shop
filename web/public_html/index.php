<?php
declare(strict_types=1);

/**
 * Front controller. Trên Hostinger: public_html/ là thư mục gốc web;
 * app/, bin/, migrations/, storage/ nằm cạnh public_html (ngoài vùng công khai).
 */
$appDir = is_dir(__DIR__ . '/../app') ? __DIR__ . '/../app' : __DIR__ . '/../xuong/app';
require $appDir . '/bootstrap.php';

use App\Core\ApiError;
use App\Core\Audit;
use App\Core\Http;
use App\Core\Router;
use App\Core\Session;
use App\Core\View;
use App\Http\AccountController;
use App\Http\Admin;
use App\Http\ApiController;
use App\Http\StoreController;
use App\Http\SyncController;

$method = $_SERVER['REQUEST_METHOD'] ?? 'GET';
$path = $_SERVER['REQUEST_URI'] ?? '/';
$isApi = str_starts_with($path, '/api/');
$isSync = str_starts_with($path, '/api/sync/');

// Một nội dung — một địa chỉ: www.tenmien.vn ↔ tenmien.vn → 301 về tên miền trong base_url.
// Chỉ khi hai tên miền khác nhau đúng phần "www." — cấu hình sai cũng không gây vòng lặp chuyển hướng.
$canonHost = strtolower((string)parse_url((string)config('base_url'), PHP_URL_HOST));
$reqHost = strtolower(preg_replace('/:\d+$/', '', (string)($_SERVER['HTTP_HOST'] ?? '')));
if ($canonHost !== '' && $reqHost !== $canonHost && ($reqHost === 'www.' . $canonHost || 'www.' . $reqHost === $canonHost)
    && ($method === 'GET' || $method === 'HEAD') && !$isApi) {
    header('Location: ' . rtrim((string)config('base_url'), '/') . $path, true, 301);
    exit;
}

// "/tra-tui-loc.html/" → 301 "/tra-tui-loc.html" (tránh trùng lặp trên Google)
$pathOnly = (string)parse_url($path, PHP_URL_PATH);
if (($method === 'GET' || $method === 'HEAD') && strlen($pathOnly) > 1 && str_ends_with($pathOnly, '/') && !$isApi && !str_starts_with($pathOnly, '/admin')) {
    $qs = (string)parse_url($path, PHP_URL_QUERY);
    header('Location: ' . (rtrim($pathOnly, '/') ?: '/') . ($qs !== '' ? '?' . $qs : ''), true, 301);
    exit;
}

if (!$isSync) {
    Session::start();
}
Http::securityHeaders();

$r = new Router();

// ---------------- Cửa hàng — địa chỉ một cấp, đuôi .html (App\Domain\Urls)
use App\Domain\Urls;
$F = Urls::FIXED;
$r->get('/', [StoreController::class, 'home']);
$r->get('/' . $F['search'] . '.html', [StoreController::class, 'search']);
$r->get('/' . $F['flash'] . '.html', [StoreController::class, 'flashSale']);
$r->get('/' . $F['cart'] . '.html', [StoreController::class, 'cart']);
$r->get('/' . $F['checkout'] . '.html', [StoreController::class, 'checkout']);
$r->get('/' . $F['blog'] . '.html', [StoreController::class, 'blogIndex']);
$r->get('/' . $F['faq'] . '.html', [StoreController::class, 'faq']);
$r->get('/' . $F['account'] . '.html', [AccountController::class, 'show']);
$r->get('/' . $F['login'] . '.html', [AccountController::class, 'loginForm']);
$r->get('/' . $F['deletion'] . '.html', [AccountController::class, 'deletionStatus']);
$r->get('/' . Urls::ORDER_PREFIX . '{code}.html', [StoreController::class, 'orderConfirm']);
$r->get('/sitemap.xml', [StoreController::class, 'sitemap']);
$r->get('/robots.txt', [StoreController::class, 'robots']);
$r->get('/{slug}.html', [StoreController::class, 'resolve']); // danh mục / sản phẩm / bài viết / trang — đặt SAU các trang cố định

// Địa chỉ cũ (trước 11/2026) → 301 sang địa chỉ mới, giữ nguyên tham số truy vấn
$moved = function (string $to): void {
    $qs = (string)parse_url($_SERVER['REQUEST_URI'] ?? '', PHP_URL_QUERY);
    Http::redirect($to . ($qs !== '' ? (str_contains($to, '?') ? '&' : '?') . $qs : ''), 301);
};
foreach (['/tim-kiem' => 'search', '/flash-sale' => 'flash', '/gio-hang' => 'cart', '/thanh-toan' => 'checkout', '/blog' => 'blog',
          '/hoi-dap' => 'faq', '/tai-khoan' => 'account', '/tai-khoan/dang-nhap' => 'login', '/tai-khoan/trang-thai-xoa' => 'deletion'] as $old => $key) {
    $r->get($old, fn() => $moved(Urls::fixed($key)));
}
$r->get('/don-hang/{code}', fn(string $code) => $moved(Urls::order($code)));
foreach (Urls::LEGACY_PREFIX as $type => $prefix) {
    $r->get($prefix . '{slug}', function (string $slug) use ($type, $moved) {
        $to = Urls::legacyTarget($type, $slug); // Router đã giải mã %xx
        if ($to === null) throw ApiError::notFound('Trang này không còn tồn tại.');
        $moved($to);
    });
}

// ---------------- Tài khoản khách (đăng nhập tùy chọn bằng Google / Facebook)
// Địa chỉ /auth/* đã khai báo với Google/Facebook nên giữ nguyên; các POST là đích của biểu mẫu, không phải trang.
$r->get('/auth/{provider}', [AccountController::class, 'start']);
$r->get('/auth/{provider}/callback', [AccountController::class, 'callback']);
$r->post('/auth/facebook/xoa-du-lieu', [AccountController::class, 'facebookDeletion']);
$r->post('/tai-khoan/thong-tin', [AccountController::class, 'saveProfile']);
$r->post('/tai-khoan/nhan-tin', [AccountController::class, 'consent']);
$r->post('/tai-khoan/xoa', [AccountController::class, 'delete']);
$r->post('/tai-khoan/dang-xuat', [AccountController::class, 'logout']);

// ---------------- API công khai
$r->post('/api/quote', [ApiController::class, 'quote']);
$r->post('/api/orders', [ApiController::class, 'createOrder']);
$r->post('/api/chat', [ApiController::class, 'chat']);
$r->get('/api/products', [ApiController::class, 'products']);
$r->get('/api/health', [ApiController::class, 'health']);

// ---------------- API đồng bộ (khóa API riêng)
$r->get('/api/sync/events', [SyncController::class, 'events']);
$r->get('/api/sync/snapshot', [SyncController::class, 'snapshot']);
$r->get('/api/sync/catalog', [SyncController::class, 'catalog']);
$r->get('/api/sync/feedback', [SyncController::class, 'feedback']);
$r->post('/api/sync/drafts', [SyncController::class, 'drafts']);

// ---------------- Quản trị
Admin\Routes::register($r);

try {
    $out = $r->dispatch($method, $path);
    if (is_string($out)) {
        Http::html($out);
    }
} catch (ApiError $e) {
    if ($isApi) {
        Http::json($e->toArray(), $e->status);
    }
    if (str_starts_with($path, '/admin')) {
        Admin\Base::handleError($e, $method);
    }
    Http::html(View::render('store/error', ['code' => $e->status, 'message' => $e->getMessage(), 'title' => $e->status === 404 ? 'Không tìm thấy trang' : 'Có lỗi xảy ra', 'robots' => 'noindex'], 'store/layout'), $e->status);
} catch (Throwable $e) {
    error_log((string)$e);
    Audit::error('http', 'UNHANDLED', get_class($e) . ': ' . $e->getMessage() . ' @ ' . $path);
    if ($isApi) {
        Http::json(['error' => ['code' => 'SERVER_ERROR', 'message' => 'Hệ thống đang bận, vui lòng thử lại sau ít phút.']], 500);
    }
    $msg = config('debug') ? $e->getMessage() : 'Hệ thống đang bận, vui lòng thử lại sau ít phút.';
    Http::html(View::render('store/error', ['code' => 500, 'message' => $msg, 'title' => 'Có lỗi xảy ra', 'robots' => 'noindex'], 'store/layout'), 500);
}
