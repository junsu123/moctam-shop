<?php
declare(strict_types=1);

namespace App\Http;

use App\Core\ApiError;
use App\Core\Clock;
use App\Core\Csrf;
use App\Core\Db;
use App\Core\Http;
use App\Core\RateLimiter;
use App\Core\Session;
use App\Domain\CatalogService;
use App\Domain\ChatService;
use App\Domain\OrderService;
use App\Domain\PricingService;

/** API công khai: báo giá, tạo đơn, chat, tìm kiếm (§5.3). */
final class ApiController
{
    public function quote(): never
    {
        RateLimiter::hit('quote', 120, 60);
        $b = Http::body();
        $q = PricingService::quote((array)($b['items'] ?? []), $b['voucher_code'] ?? null, $b['province'] ?? null);
        Http::json(['quote' => $q]);
    }

    public function createOrder(): never
    {
        Csrf::verify($_SERVER['HTTP_X_CSRF_TOKEN'] ?? null);
        RateLimiter::hit('order', 15, 600);
        $idem = (string)($_SERVER['HTTP_IDEMPOTENCY_KEY'] ?? '');
        $res = OrderService::create(Http::body(), Session::id(), $idem);
        $_SESSION['my_orders'][$res['order']['code']] = true; // xem xác nhận trong phiên đặt hàng
        Http::json($res, $res['replayed'] ? 200 : 201);
    }

    public function chat(): never
    {
        RateLimiter::hit('chat', 30, 60);
        $b = Http::body();
        $msg = (string)($b['message'] ?? '');
        if (trim($msg) === '') {
            throw ApiError::validation(['message' => 'Vui lòng nhập câu hỏi']);
        }
        Http::json(ChatService::answer($msg));
    }

    public function products(): never
    {
        RateLimiter::hit('search', 120, 60);
        $res = CatalogService::search((string)($_GET['q'] ?? ''), isset($_GET['category']) ? (int)$_GET['category'] : null, (int)($_GET['page'] ?? 1), min(24, max(1, (int)($_GET['per_page'] ?? 8))));
        $res['items'] = array_map(fn($p) => [
            'name' => $p['name'], 'url' => '/san-pham/' . $p['slug'], 'image' => $p['image'],
            'min_price' => (int)$p['min_price'], 'flash' => $p['flash'], 'available' => (int)$p['available'] > 0,
        ], $res['items']);
        Http::json($res);
    }

    /** Kiểm tra sống cho giám sát ngoài (không lộ chi tiết). */
    public function health(): never
    {
        $ok = (bool)Db::val('SELECT 1');
        Http::json(['ok' => $ok, 'time' => Clock::nowDb()]);
    }
}
