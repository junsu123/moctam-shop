<?php
declare(strict_types=1);

/** Tiện ích kiểm thử dùng chung (không cần PHPUnit để chạy được trên hosting). */

putenv('XUONG_DB=' . (getenv('XUONG_DB') ?: 'xuong_test'));
require __DIR__ . '/../app/bootstrap.php';

use App\Core\Auth;
use App\Core\Clock;
use App\Core\Db;
use App\Core\Session;
use App\Core\Settings;

Session::start();

function t_user(string $role): int
{
    $email = "test_$role@xuong.local";
    $id = Db::val('SELECT id FROM users WHERE email = :e', ['e' => $email]);
    if (!$id) {
        $id = Db::insert('users', ['email' => $email, 'full_name' => "Test $role", 'password_hash' => password_hash('x', PASSWORD_DEFAULT), 'role_code' => $role, 'created_at' => Clock::nowDb(), 'updated_at' => Clock::nowDb()]);
    }
    Auth::actAs((int)$id);
    return (int)$id;
}

function t_sku(string $code, int $price, int $stock): int
{
    $pid = (int)Db::val("SELECT id FROM products WHERE slug = 'test-product'");
    if (!$pid) {
        $cat = (int)Db::val('SELECT id FROM categories ORDER BY id LIMIT 1');
        $pid = Db::insert('products', ['category_id' => $cat, 'name' => 'Sản phẩm kiểm thử', 'slug' => 'test-product', 'status' => 'active', 'search_text' => 'san pham kiem thu', 'created_at' => Clock::nowDb(), 'updated_at' => Clock::nowDb()]);
    }
    $sid = Db::insert('skus', ['product_id' => $pid, 'sku_code' => $code, 'variant_label' => $code, 'price' => $price, 'status' => 'active', 'created_at' => Clock::nowDb(), 'updated_at' => Clock::nowDb()]);
    Db::insert('inventory', ['sku_id' => $sid, 'on_hand' => $stock, 'reserved' => 0, 'updated_at' => Clock::nowDb()]);
    return $sid;
}

function t_zone(int $fee = 25000): string
{
    $prov = 'Tỉnh Kiểm Thử';
    if (!Db::val('SELECT id FROM shipping_zones WHERE name = :n', ['n' => 'Vùng kiểm thử'])) {
        $z = Db::insert('shipping_zones', ['name' => 'Vùng kiểm thử', 'provinces' => json_enc([$prov]), 'is_active' => 1, 'sort_order' => 99]);
        Db::insert('shipping_rates', ['zone_id' => $z, 'fee' => $fee, 'free_from' => null, 'effective_from' => '2020-01-01 00:00:00', 'created_at' => Clock::nowDb()]);
    }
    return $prov;
}

function t_voucher(string $code, int $amount, int $min, ?int $limit): int
{
    return Db::insert('vouchers', ['code' => $code, 'amount' => $amount, 'min_subtotal' => $min, 'scope_type' => 'all', 'scope_ids' => '[]',
        'starts_at' => '2020-01-01 00:00:00', 'ends_at' => '2099-01-01 00:00:00', 'usage_limit' => $limit, 'is_active' => 1, 'created_at' => Clock::nowDb(), 'updated_at' => Clock::nowDb()]);
}

function t_input(array $items, ?string $voucher, string $method = 'cod', ?string $token = null, string $phone = '0912345678'): array
{
    return [
        'items' => $items, 'voucher_code' => $voucher, 'payment_method' => $method, 'quote_token' => $token, 'marketing_consent' => true,
        'customer' => ['name' => 'Nguyễn Văn Test', 'phone' => $phone, 'province' => t_zone(), 'address' => '12 Đường Kiểm Thử, Phường A'],
    ];
}

function t_key(): string
{
    return 'k_' . bin2hex(random_bytes(12));
}

function inv(int $skuId): array
{
    return array_map('intval', Db::one('SELECT on_hand, reserved FROM inventory WHERE sku_id = :s', ['s' => $skuId]));
}

/** Chạy N tiến trình worker đồng thời; trả mảng kết quả JSON. */
function t_parallel(array $jobs): array
{
    $start = microtime(true) + 0.6;
    $procs = [];
    foreach ($jobs as $i => $job) {
        $job['start_at'] = $start;
        $cmd = [PHP_BINARY, __DIR__ . '/worker.php', base64_encode(json_enc($job))];
        $procs[$i] = proc_open($cmd, [1 => ['pipe', 'w'], 2 => ['pipe', 'w']], $pipes[$i], null, ['XUONG_DB' => getenv('XUONG_DB')] + getenv());
    }
    $out = [];
    foreach ($procs as $i => $p) {
        $stdout = stream_get_contents($pipes[$i][1]);
        $stderr = stream_get_contents($pipes[$i][2]);
        proc_close($p);
        $out[$i] = json_decode($stdout, true) ?? ['raw' => $stdout, 'stderr' => $stderr];
    }
    return $out;
}

$GLOBALS['T_RESULTS'] = [];
function check(string $id, string $name, callable $fn): void
{
    $t0 = microtime(true);
    try {
        $notes = $fn();
        $GLOBALS['T_RESULTS'][] = [$id, $name, 'ĐẠT', is_string($notes) ? $notes : '', round((microtime(true) - $t0) * 1000)];
        echo "  ✔ $id $name" . (is_string($notes) && $notes ? " — $notes" : '') . "\n";
    } catch (Throwable $e) {
        $GLOBALS['T_RESULTS'][] = [$id, $name, 'KHÔNG ĐẠT', $e->getMessage() . ' @' . basename($e->getFile()) . ':' . $e->getLine(), 0];
        echo "  ✘ $id $name — " . $e->getMessage() . ' @' . basename($e->getFile()) . ':' . $e->getLine() . "\n";
    } finally {
        Clock::set(null);
        Settings::flush();
        Auth::actAs(null);
    }
}

function ok(bool $cond, string $msg): void
{
    if (!$cond) throw new RuntimeException('Giả định sai: ' . $msg);
}

function expect_error(string $code, callable $fn): \App\Core\ApiError
{
    try {
        $fn();
    } catch (\App\Core\ApiError $e) {
        if ($e->errorCode !== $code) throw new RuntimeException("Mong lỗi $code, nhận {$e->errorCode}: {$e->getMessage()}");
        return $e;
    }
    throw new RuntimeException("Mong lỗi $code nhưng không có lỗi");
}
