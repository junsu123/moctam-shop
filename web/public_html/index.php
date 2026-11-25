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

if (!$isSync) {
    Session::start();
}
Http::securityHeaders();

$r = new Router();

// ---------------- Cửa hàng
$r->get('/', [StoreController::class, 'home']);
$r->get('/danh-muc/{slug}', [StoreController::class, 'category']);
$r->get('/tim-kiem', [StoreController::class, 'search']);
$r->get('/san-pham/{slug}', [StoreController::class, 'product']);
$r->get('/flash-sale', [StoreController::class, 'flashSale']);
$r->get('/gio-hang', [StoreController::class, 'cart']);
$r->get('/thanh-toan', [StoreController::class, 'checkout']);
$r->get('/don-hang/{code}', [StoreController::class, 'orderConfirm']);
$r->get('/blog', [StoreController::class, 'blogIndex']);
$r->get('/blog/{slug}', [StoreController::class, 'blogShow']);
$r->get('/hoi-dap', [StoreController::class, 'faq']);
$r->get('/chinh-sach/{slug}', [StoreController::class, 'page']);
$r->get('/sitemap.xml', [StoreController::class, 'sitemap']);

// ---------------- Tài khoản khách (đăng nhập tùy chọn bằng Google / Facebook)
$r->get('/tai-khoan/dang-nhap', [AccountController::class, 'loginForm']);
$r->get('/auth/{provider}', [AccountController::class, 'start']);
$r->get('/auth/{provider}/callback', [AccountController::class, 'callback']);
$r->post('/auth/facebook/xoa-du-lieu', [AccountController::class, 'facebookDeletion']);
$r->get('/tai-khoan/trang-thai-xoa', [AccountController::class, 'deletionStatus']);
$r->get('/tai-khoan', [AccountController::class, 'show']);
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
    Http::html(View::render('store/error', ['code' => $e->status, 'message' => $e->getMessage(), 'title' => 'Lỗi'], 'store/layout'), $e->status);
} catch (Throwable $e) {
    error_log((string)$e);
    Audit::error('http', 'UNHANDLED', get_class($e) . ': ' . $e->getMessage() . ' @ ' . $path);
    if ($isApi) {
        Http::json(['error' => ['code' => 'SERVER_ERROR', 'message' => 'Hệ thống đang bận, vui lòng thử lại sau ít phút.']], 500);
    }
    $msg = config('debug') ? $e->getMessage() : 'Hệ thống đang bận, vui lòng thử lại sau ít phút.';
    Http::html(View::render('store/error', ['code' => 500, 'message' => $msg, 'title' => 'Lỗi'], 'store/layout'), 500);
}
