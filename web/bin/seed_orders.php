<?php
declare(strict_types=1);

/**
 * CHỈ DÙNG MÔI TRƯỜNG THỬ: tạo đơn lịch sử đã giao (90 ngày) để thử dịch vụ Python
 * (gợi ý mua kèm, chăm sóc lại) và màn hình quản trị.  php bin/seed_orders.php [số_khách=24]
 */
require __DIR__ . '/../app/bootstrap.php';

use App\Core\Auth;
use App\Core\Clock;
use App\Core\Db;
use App\Core\Session;
use App\Domain\OrderService;
use App\Domain\PaymentService;
use App\Domain\PricingService;

Session::start();
$admin = (int)Db::val("SELECT id FROM users WHERE role_code = 'admin' ORDER BY id LIMIT 1");
if (!$admin) { fwrite(STDERR, "Cần một tài khoản admin (seed.php --demo-users).\n"); exit(1); }
mt_srand(42);
$n = (int)($argv[1] ?? 24);
$skus = Db::all("SELECT s.id, s.product_id, p.category_id FROM skus s JOIN products p ON p.id = s.product_id JOIN inventory i ON i.sku_id = s.id WHERE s.status='active' AND i.on_hand > 20");
$byP = [];
foreach ($skus as $s) $byP[$s['product_id']][] = (int)$s['id'];
// cặp hay mua cùng (để tác nhân mua kèm có tín hiệu)
$combos = [[1, 3], [6, 8], [14, 16], [10, 8], [2, 4], [1, 11]];
$names = ['Nguyễn An', 'Trần Bình', 'Lê Chi', 'Phạm Dung', 'Hoàng Giang', 'Vũ Hà', 'Đặng Khoa', 'Bùi Lan', 'Đỗ Minh', 'Ngô Nga', 'Dương Phúc', 'Lý Quỳnh'];
$provinces = ['Hà Nội', 'TP. Hồ Chí Minh', 'Đà Nẵng', 'Hải Phòng', 'Cần Thơ', 'Huế'];
$made = 0;
for ($c = 0; $c < $n; $c++) {
    $phone = '09' . str_pad((string)(10000000 + $c * 7919), 8, '0', STR_PAD_LEFT);
    $visits = mt_rand(1, 3);
    $start = 95 - mt_rand(0, 20);
    $gap = [21, 28, 30, 35, 45][mt_rand(0, 4)];
    for ($v = 0; $v < $visits; $v++) {
        $daysAgo = $start - $v * $gap;
        if ($daysAgo < 3) break;
        Clock::set(new DateTimeImmutable("-{$daysAgo} days 10:00", new DateTimeZone('UTC')));
        $combo = $combos[($c + $v) % count($combos)];
        $items = [];
        foreach ($combo as $pid) if (!empty($byP[$pid])) $items[] = ['sku_id' => $byP[$pid][0], 'qty' => 1];
        if (mt_rand(0, 2) === 0) { $rp = array_rand($byP); $items[] = ['sku_id' => $byP[$rp][0], 'qty' => 1]; }
        $prov = $provinces[$c % count($provinces)];
        $method = mt_rand(0, 1) ? 'cod' : 'vietqr';
        $q = PricingService::quote($items, null, $prov);
        if ($q['issues']) continue;
        Auth::actAs(null);
        $r = OrderService::create(['items' => $items, 'payment_method' => $method, 'quote_token' => $q['quote_token'], 'marketing_consent' => $c % 4 !== 0,
            'customer' => ['name' => $names[$c % count($names)], 'phone' => $phone, 'province' => $prov, 'address' => (10 + $c) . ' Đường Mẫu, Phường ' . ($c % 9 + 1)]], 'seed-' . $c, 'seed_' . $c . '_' . $v . '_' . bin2hex(random_bytes(4)));
        $oid = (int)Db::val('SELECT id FROM orders WHERE code = :c', ['c' => $r['order']['code']]);
        Auth::actAs($admin);
        if ($method === 'vietqr') {
            PaymentService::recordVietQr(['order_code' => $r['order']['code'], 'amount' => $r['order']['total'], 'bank_txn_id' => 'FT' . $oid . 'X', 'source' => 'VCB',
                'received_at' => Clock::toLocalInput(Clock::nowDb()), 'transfer_content' => $r['order']['code']]);
        }
        OrderService::transition($oid, 'confirmed');
        Clock::set(Clock::now()->modify('+5 hours'));
        OrderService::transition($oid, 'shipping', null, ['carrier_name' => 'GHN', 'tracking_code' => 'GHN' . $oid]);
        Clock::set(Clock::now()->modify('+2 days'));
        OrderService::transition($oid, 'delivered');
        if ($method === 'cod') {
            PaymentService::recordCod($oid, ['amount' => $r['order']['total'], 'bank_txn_id' => 'COD-' . $oid, 'source' => 'GHN', 'received_at' => Clock::toLocalInput(Clock::nowDb())]);
        }
        $made++;
    }
}
Clock::set(null);
echo "Đã tạo $made đơn đã giao trong 90 ngày qua.\n";
