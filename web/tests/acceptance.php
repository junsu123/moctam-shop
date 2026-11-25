<?php
declare(strict_types=1);

/**
 * Ca nghiệm thu AT-01 … AT-11 (đặc tả §8) + kiểm tra quy tắc nghiệp vụ bổ sung.
 * CHỈ chạy trên CSDL kiểm thử — tệp sẽ XÓA và tạo lại CSDL:
 *   XUONG_DB=xuong_test php tests/acceptance.php [--report=../docs/KET-QUA-NGHIEM-THU.md]
 */
putenv('XUONG_DB=' . (getenv('XUONG_DB') ?: 'xuong_test'));
$dbName = getenv('XUONG_DB');
if (!preg_match('/test/', $dbName)) {
    fwrite(STDERR, "Từ chối: tên CSDL phải chứa 'test'.\n");
    exit(1);
}
$cfg = require (getenv('XUONG_CONFIG') ?: __DIR__ . '/../app/config.php');
$admin = new PDO("mysql:host={$cfg['db']['host']};port={$cfg['db']['port']}", $cfg['db']['user'], $cfg['db']['password']);
$admin->exec("DROP DATABASE IF EXISTS `$dbName`; CREATE DATABASE `$dbName` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci");
passthru(PHP_BINARY . ' ' . escapeshellarg(__DIR__ . '/../bin/migrate.php') . ' > /dev/null');
passthru(PHP_BINARY . ' ' . escapeshellarg(__DIR__ . '/../bin/seed.php') . ' > /dev/null');

require __DIR__ . '/lib.php';

use App\Core\ApiError;
use App\Core\Auth;
use App\Core\Clock;
use App\Core\Db;
use App\Core\Html;
use App\Domain\Bm25;
use App\Domain\ChatService;
use App\Domain\ContentService;
use App\Domain\DraftInbox;
use App\Domain\OrderService;
use App\Domain\PaymentService;
use App\Domain\PricingService;
use App\Domain\PromotionService;
use App\Domain\SyncService;
use App\Domain\VietQr;

echo "Chạy nghiệm thu trên CSDL `$dbName`\n";

// ---------------------------------------------------------------- §4.1 ví dụ báo giá
check('BR-01', 'Công thức tổng: 180.000 − 20.000 + 25.000 = 185.000 ₫', function () {
    $sku = t_sku('T-QUOTE', 90000, 10);
    t_voucher('GIAM20', 20000, 150000, null);
    $q = PricingService::quote([['sku_id' => $sku, 'qty' => 2]], 'GIAM20', t_zone(25000));
    ok($q['goods_subtotal'] === 180000, 'tiền hàng 180.000, nhận ' . $q['goods_subtotal']);
    ok($q['discount'] === 20000, 'giảm 20.000');
    ok($q['shipping']['fee'] === 25000, 'phí giao 25.000');
    ok($q['total'] === 185000, 'tổng 185.000, nhận ' . $q['total']);
    $r = OrderService::create(t_input([['sku_id' => $sku, 'qty' => 2]], 'GIAM20', 'cod', $q['quote_token']), 'sess-br01', t_key());
    ok($r['order']['total'] === 185000, 'đơn lưu đúng tổng');
    return 'đơn ' . $r['order']['code'] . ' = ' . money($r['order']['total']);
});

check('BR-02', 'Voucher: đơn tối thiểu tính trên hàng đủ điều kiện sau Flash Sale; giảm ≤ tiền hàng đủ điều kiện', function () {
    $a = t_sku('T-FSV-A', 100000, 10);
    $b = t_sku('T-FSV-B', 30000, 10);
    t_voucher('LON50', 50000, 0, null);
    $fs = Db::insert('flash_sales', ['name' => 'FS test', 'starts_at' => '2020-01-01 00:00:00', 'ends_at' => '2099-01-01 00:00:00', 'allow_voucher' => 0, 'is_active' => 1, 'created_at' => Clock::nowDb(), 'updated_at' => Clock::nowDb()]);
    Db::insert('flash_sale_items', ['flash_sale_id' => $fs, 'sku_id' => $a, 'sale_price' => 80000]);
    $q = PricingService::quote([['sku_id' => $a, 'qty' => 1], ['sku_id' => $b, 'qty' => 1]], 'LON50', t_zone());
    ok($q['goods_subtotal'] === 110000, 'tiền hàng sau FS = 80.000 + 30.000');
    ok($q['voucher']['eligible_subtotal'] === 30000, 'dòng FS không tính vào voucher');
    ok($q['discount'] === 30000, 'giảm tối đa bằng tiền hàng đủ điều kiện (30.000), nhận ' . $q['discount']);
    t_voucher('MIN50K', 10000, 50000, null);
    $q2 = PricingService::quote([['sku_id' => $a, 'qty' => 1], ['sku_id' => $b, 'qty' => 1]], 'MIN50K', t_zone());
    ok($q2['voucher']['error_code'] === 'VOUCHER_MIN_NOT_MET' && $q2['discount'] === 0, 'không đạt tối thiểu trên hàng đủ điều kiện');
});

check('BR-03', 'Mỗi SKU tối đa một Flash Sale hiệu lực tại một thời điểm', function () {
    t_user('operations');
    $s = t_sku('T-FS-OVL', 50000, 5);
    PromotionService::saveFlashSale(null, ['name' => 'A', 'starts_at' => '2030-01-01T08:00', 'ends_at' => '2030-01-03T08:00', 'is_active' => 1], [$s => 40000]);
    expect_error('VALIDATION_ERROR', fn() => PromotionService::saveFlashSale(null, ['name' => 'B', 'starts_at' => '2030-01-02T08:00', 'ends_at' => '2030-01-04T08:00', 'is_active' => 1], [$s => 39000]));
    PromotionService::saveFlashSale(null, ['name' => 'C', 'starts_at' => '2030-01-03T08:00', 'ends_at' => '2030-01-05T08:00', 'is_active' => 1], [$s => 39000]);
    return 'chồng lấn bị từ chối, nối tiếp được chấp nhận';
});

// ---------------------------------------------------------------- AT-01
check('AT-01', 'Hai khách đặt cùng SKU chỉ còn 1 đơn vị (song song)', function () {
    $sku = t_sku('T-AT01', 50000, 1);
    $q = PricingService::quote([['sku_id' => $sku, 'qty' => 1]], null, t_zone());
    $res = t_parallel([
        ['action' => 'create_order', 'input' => t_input([['sku_id' => $sku, 'qty' => 1]], null, 'cod', $q['quote_token'], '0911111111'), 'session' => 's1', 'key' => t_key()],
        ['action' => 'create_order', 'input' => t_input([['sku_id' => $sku, 'qty' => 1]], null, 'cod', $q['quote_token'], '0922222222'), 'session' => 's2', 'key' => t_key()],
    ]);
    $okN = count(array_filter($res, fn($r) => $r['ok'] ?? false));
    $oos = count(array_filter($res, fn($r) => ($r['error'] ?? '') === 'OUT_OF_STOCK'));
    ok($okN === 1 && $oos === 1, 'kết quả: ' . json_encode($res));
    $i = inv($sku);
    ok($i['on_hand'] - $i['reserved'] === 0 && $i['reserved'] === 1, 'tồn khả dụng 0, giữ 1: ' . json_encode($i));
    return '1 đơn thành công, 1 đơn nhận OUT_OF_STOCK, tồn khả dụng = 0';
});

// ---------------------------------------------------------------- AT-02
check('AT-02', 'Flash Sale kết thúc sau khi khách xem báo giá', function () {
    $sku = t_sku('T-AT02', 100000, 10);
    $fs = Db::insert('flash_sales', ['name' => 'FS ngắn', 'starts_at' => Clock::db(Clock::now()->modify('-1 hour')), 'ends_at' => Clock::db(Clock::now()->modify('+10 minutes')), 'allow_voucher' => 0, 'is_active' => 1, 'created_at' => Clock::nowDb(), 'updated_at' => Clock::nowDb()]);
    Db::insert('flash_sale_items', ['flash_sale_id' => $fs, 'sku_id' => $sku, 'sale_price' => 70000]);
    $q = PricingService::quote([['sku_id' => $sku, 'qty' => 1]], null, t_zone());
    ok($q['lines'][0]['unit_price'] === 70000, 'báo giá Flash Sale 70.000');
    Clock::set(Clock::now()->modify('+11 minutes')); // FS đã kết thúc, báo giá (15') vẫn còn hạn
    $e = expect_error('QUOTE_CHANGED', fn() => OrderService::create(t_input([['sku_id' => $sku, 'qty' => 1]], null, 'cod', $q['quote_token']), 'sess-at02', t_key()));
    $newQ = $e->data['quote'];
    ok($newQ['lines'][0]['unit_price'] === 100000, 'máy chủ trả giá hiện hành 100.000');
    ok((int)Db::val("SELECT COUNT(*) FROM order_items WHERE sku_id = :s", ['s' => $sku]) === 0, 'chưa tạo đơn');
    $r = OrderService::create(t_input([['sku_id' => $sku, 'qty' => 1]], null, 'cod', $newQ['quote_token']), 'sess-at02', t_key());
    ok($r['order']['goods_subtotal'] === 100000, 'đơn tạo sau khi khách xác nhận giá mới');
    return 'QUOTE_CHANGED → khách xác nhận → tạo đơn ' . money(100000);
});

// ---------------------------------------------------------------- AT-03
check('AT-03', 'Mạng ngắt sau khi tạo đơn, khách gửi lại cùng yêu cầu', function () {
    $sku = t_sku('T-AT03', 80000, 10);
    $vid = t_voucher('LAI10', 10000, 50000, 100);
    $q = PricingService::quote([['sku_id' => $sku, 'qty' => 2]], 'LAI10', t_zone());
    $in = t_input([['sku_id' => $sku, 'qty' => 2]], 'LAI10', 'vietqr', $q['quote_token']);
    $key = t_key();
    $r1 = OrderService::create($in, 'sess-at03', $key);
    $r2 = OrderService::create($in, 'sess-at03', $key);
    ok($r1['order']['code'] === $r2['order']['code'] && $r2['replayed'] === true, 'trả đúng mã đơn ban đầu');
    ok(inv($sku)['reserved'] === 2, 'chỉ giữ tồn một lần');
    ok((int)Db::val('SELECT reserved_count FROM vouchers WHERE id = :v', ['v' => $vid]) === 1, 'chỉ giữ một lượt voucher');
    $in2 = $in;
    $in2['items'][0]['qty'] = 3;
    expect_error('IDEMPOTENCY_CONFLICT', fn() => OrderService::create($in2, 'sess-at03', $key));
    // Gửi trùng ĐỒNG THỜI
    $q2 = PricingService::quote([['sku_id' => $sku, 'qty' => 1]], null, t_zone());
    $in3 = t_input([['sku_id' => $sku, 'qty' => 1]], null, 'cod', $q2['quote_token'], '0933333333');
    $k3 = t_key();
    $res = t_parallel([
        ['action' => 'create_order', 'input' => $in3, 'session' => 'sess-dup', 'key' => $k3],
        ['action' => 'create_order', 'input' => $in3, 'session' => 'sess-dup', 'key' => $k3],
        ['action' => 'create_order', 'input' => $in3, 'session' => 'sess-dup', 'key' => $k3],
    ]);
    $codes = array_unique(array_column($res, 'code'));
    ok(count($codes) === 1 && count(array_filter($res, fn($r) => $r['ok'] ?? false)) === 3, 'gửi trùng đồng thời: ' . json_encode($res));
    ok(inv($sku)['reserved'] === 3, 'tổng giữ tồn = 2 + 1');
    return 'gửi lại tuần tự và 3 yêu cầu trùng đồng thời đều trả 1 mã đơn; khóa trùng khác nội dung → IDEMPOTENCY_CONFLICT';
});

// ---------------------------------------------------------------- AT-04
check('AT-04', 'Hai đơn dùng lượt voucher cuối cùng (song song)', function () {
    $sku = t_sku('T-AT04', 100000, 10);
    $vid = t_voucher('CUOI1', 20000, 0, 1);
    $q = PricingService::quote([['sku_id' => $sku, 'qty' => 1]], 'CUOI1', t_zone());
    ok($q['discount'] === 20000, 'cả hai thấy được giảm');
    $res = t_parallel([
        ['action' => 'create_order', 'input' => t_input([['sku_id' => $sku, 'qty' => 1]], 'CUOI1', 'cod', $q['quote_token'], '0944444444'), 'session' => 'a', 'key' => t_key()],
        ['action' => 'create_order', 'input' => t_input([['sku_id' => $sku, 'qty' => 1]], 'CUOI1', 'cod', $q['quote_token'], '0955555555'), 'session' => 'b', 'key' => t_key()],
    ]);
    $won = array_values(array_filter($res, fn($r) => $r['ok'] ?? false));
    $lost = array_values(array_filter($res, fn($r) => ($r['error'] ?? '') === 'QUOTE_CHANGED'));
    ok(count($won) === 1 && count($lost) === 1, json_encode($res));
    ok($lost[0]['details']['quote']['discount'] === 0 && $lost[0]['details']['quote']['voucher']['error_code'] === 'VOUCHER_EXHAUSTED', 'đơn thua nhận báo giá mới không có giảm giá');
    ok((int)Db::val('SELECT reserved_count FROM vouchers WHERE id = :v', ['v' => $vid]) === 1, 'đúng 1 lượt được giữ');
    ok(inv($sku)['reserved'] === 1, 'đơn thua không giữ tồn (giao dịch hoàn tác)');
    return 'một đơn giữ lượt; đơn còn lại nhận QUOTE_CHANGED (VOUCHER_EXHAUSTED)';
});

// ---------------------------------------------------------------- AT-05
check('AT-05', 'VietQR chuyển thiếu / chuyển sau khi đơn hết hạn', function () {
    $sku = t_sku('T-AT05', 120000, 10);
    $q = PricingService::quote([['sku_id' => $sku, 'qty' => 1]], null, t_zone());
    $r = OrderService::create(t_input([['sku_id' => $sku, 'qty' => 1]], null, 'vietqr', $q['quote_token']), 'sess-at05', t_key());
    $code = $r['order']['code'];
    $oid = (int)Db::val('SELECT id FROM orders WHERE code = :c', ['c' => $code]);
    t_user('reconciliation');
    $res = PaymentService::recordVietQr(['order_code' => $code, 'amount' => 100000, 'bank_txn_id' => 'FT001', 'source' => 'VCB', 'received_at' => '2026-11-25T10:00', 'transfer_content' => $code]);
    ok($res['discrepancies'] === ['underpaid'], 'ghi nhận sai lệch chuyển thiếu');
    ok(Db::val('SELECT status FROM orders WHERE id = :id', ['id' => $oid]) === 'pending', 'đơn vẫn chờ xác nhận');
    t_user('operations');
    expect_error('PAYMENT_NOT_RECONCILED', fn() => OrderService::transition($oid, 'confirmed'));
    t_user('reconciliation');
    expect_error('DUPLICATE_TXN', fn() => PaymentService::recordVietQr(['order_code' => $code, 'amount' => 25000, 'bank_txn_id' => 'FT001', 'source' => 'VCB', 'received_at' => '2026-11-25T10:00']));

    // Chuyển sau hạn: đơn thứ hai hết hạn, tác vụ hủy, tiền đến sau
    $q2 = PricingService::quote([['sku_id' => $sku, 'qty' => 1]], null, t_zone());
    $r2 = OrderService::create(t_input([['sku_id' => $sku, 'qty' => 1]], null, 'vietqr', $q2['quote_token'], '0966666666'), 'sess-at05b', t_key());
    $oid2 = (int)Db::val('SELECT id FROM orders WHERE code = :c', ['c' => $r2['order']['code']]);
    Clock::set(Clock::now()->modify('+25 hours'));
    Auth::actAs(null);
    $exp = OrderService::expireDue();
    ok(Db::val('SELECT status FROM orders WHERE id = :id', ['id' => $oid2]) === 'cancelled', 'đơn hết hạn bị hủy: ' . json_encode($exp));
    ok(Db::val('SELECT status FROM orders WHERE id = :id', ['id' => $oid]) === 'pending' && (int)Db::val('SELECT needs_review FROM orders WHERE id = :id', ['id' => $oid]) === 1, 'đơn đã có khoản thu → chuyển nhân viên, không tự hủy');
    t_user('reconciliation');
    $late = PaymentService::recordVietQr(['order_code' => $r2['order']['code'], 'amount' => (int)$r2['order']['total'], 'bank_txn_id' => 'FT002', 'source' => 'VCB', 'received_at' => Clock::toLocalInput(Clock::nowDb()), 'transfer_content' => $r2['order']['code']]);
    ok(in_array('after_cancel', $late['discrepancies'], true), 'tiền đến sau hủy vào danh sách đối soát');
    ok(Db::val('SELECT status FROM orders WHERE id = :id', ['id' => $oid2]) === 'cancelled', 'hệ thống không tự chuyển đơn sang sẵn sàng giao');
    return 'thiếu tiền → sai lệch underpaid, chặn xác nhận; tiền sau hủy → after_cancel, đơn giữ trạng thái Đã hủy';
});

// ---------------------------------------------------------------- AT-06
check('AT-06', 'Hủy trước khi xuất / hàng quay về sau giao thất bại', function () {
    $sku = t_sku('T-AT06', 60000, 10);
    $mk = function (int $qty, string $phone) use ($sku) {
        $q = PricingService::quote([['sku_id' => $sku, 'qty' => $qty]], null, t_zone());
        $r = OrderService::create(t_input([['sku_id' => $sku, 'qty' => $qty]], null, 'cod', $q['quote_token'], $phone), 'sess-' . $phone, t_key());
        return (int)Db::val('SELECT id FROM orders WHERE code = :c', ['c' => $r['order']['code']]);
    };
    $o1 = $mk(3, '0977000001');
    ok(inv($sku) === ['on_hand' => 10, 'reserved' => 3], 'giữ 3');
    t_user('operations');
    OrderService::transition($o1, 'confirmed');
    OrderService::transition($o1, 'cancelled', 'Khách đổi ý');
    ok(inv($sku) === ['on_hand' => 10, 'reserved' => 0], 'hủy trước xuất giải phóng tồn giữ');

    $o2 = $mk(2, '0977000002');
    OrderService::transition($o2, 'confirmed');
    OrderService::transition($o2, 'shipping', null, ['carrier_name' => 'GHN', 'tracking_code' => 'GHN123']);
    ok(inv($sku) === ['on_hand' => 8, 'reserved' => 0], 'bàn giao trừ tồn thực tế và tồn giữ');
    expect_error('INVALID_TRANSITION', fn() => OrderService::transition($o2, 'cancelled', 'x'));
    t_user('warehouse');
    OrderService::transition($o2, 'returning', 'Giao thất bại — khách không nghe máy');
    $itemId = (int)Db::val('SELECT id FROM order_items WHERE order_id = :o', ['o' => $o2]);
    OrderService::transition($o2, 'returned', 'Kiểm hàng', ['inspection' => [$itemId => ['ok' => 1, 'reject' => 1]]]);
    ok(inv($sku) === ['on_hand' => 9, 'reserved' => 0], 'chỉ cộng 1 đơn vị đạt kiểm: ' . json_encode(inv($sku)));
    $mv = (int)Db::val("SELECT COUNT(*) FROM inventory_movements WHERE order_id = :o AND type = 'ship'", ['o' => $o2]);
    ok($mv === 1, 'mỗi lần chuyển trạng thái chỉ ghi biến động kho một lần');
    return 'hủy trước xuất: tồn giữ 3 → 0; hoàn hàng 2 (1 đạt, 1 hỏng): tồn 8 → 9';
});

// ---------------------------------------------------------------- AT-07
check('AT-07', 'Nhân viên kho thử duyệt hoàn tiền khi chưa được cấp quyền', function () {
    $sku = t_sku('T-AT07', 100000, 5);
    $q = PricingService::quote([['sku_id' => $sku, 'qty' => 1]], null, t_zone());
    $r = OrderService::create(t_input([['sku_id' => $sku, 'qty' => 1]], null, 'vietqr', $q['quote_token'], '0988000007'), 'sess-at07', t_key());
    $oid = (int)Db::val('SELECT id FROM orders WHERE code = :c', ['c' => $r['order']['code']]);
    t_user('reconciliation');
    PaymentService::recordVietQr(['order_code' => $r['order']['code'], 'amount' => (int)$r['order']['total'], 'bank_txn_id' => 'FT-AT07', 'source' => 'VCB', 'received_at' => Clock::toLocalInput(Clock::nowDb()), 'transfer_content' => $r['order']['code']]);
    t_user('operations');
    OrderService::transition($oid, 'cancelled', 'Hết hàng thực tế');
    $refundId = (int)Db::val("SELECT id FROM refunds WHERE order_id = :o AND status = 'pending'", ['o' => $oid]);
    ok($refundId > 0, 'hủy đơn đã thu tiền tạo việc hoàn tiền');
    $before = Db::one('SELECT amount_received, amount_refunded, payment_status FROM orders WHERE id = :id', ['id' => $oid]);
    t_user('warehouse');
    expect_error('FORBIDDEN', fn() => PaymentService::completeRefund($refundId, ['refund_txn_ref' => 'HACK']));
    expect_error('FORBIDDEN', fn() => PaymentService::createRefund($oid, 1000, 'thử'));
    $after = Db::one('SELECT amount_received, amount_refunded, payment_status FROM orders WHERE id = :id', ['id' => $oid]);
    ok($before == $after && Db::val('SELECT status FROM refunds WHERE id = :id', ['id' => $refundId]) === 'pending', 'dữ liệu tài chính giữ nguyên');
    ok((int)Db::val("SELECT COUNT(*) FROM audit_logs WHERE action = 'permission_denied'") >= 2, 'ghi nhật ký từ chối');
    t_user('reconciliation');
    PaymentService::completeRefund($refundId, ['refund_txn_ref' => 'FT-HOAN-01']);
    ok(Db::val('SELECT payment_status FROM orders WHERE id = :id', ['id' => $oid]) === 'refunded', 'người có quyền hoàn được');
    expect_error('REFUND_EXCEEDS_RECEIVED', fn() => PaymentService::createRefund($oid, 1, 'vượt'));
    return 'máy chủ trả FORBIDDEN, số liệu không đổi; tổng hoàn không vượt tiền thực nhận';
});

// ---------------------------------------------------------------- AT-08 (phía website)
check('AT-08a', 'Con trỏ đồng bộ theo thứ tự commit, nhận cả cập nhật đơn cũ', function () {
    $cursor = (int)Db::val('SELECT last_seq FROM sync_counter WHERE id = 1');
    // Giao dịch A lấy seq trước nhưng commit chậm; B bắt đầu sau, phải chờ A
    $res = t_parallel([
        ['action' => 'emit_slow', 'entity' => 1, 'who' => 'A', 'delay_before' => 0, 'hold_ms' => 700],
        ['action' => 'emit_slow', 'entity' => 2, 'who' => 'B', 'delay_before' => 150, 'hold_ms' => 0],
    ]);
    ok($res[0]['ok'] && $res[1]['ok'], json_encode($res));
    ok($res[0]['seq'] < $res[1]['seq'] && $res[0]['committed_at'] <= $res[1]['committed_at'], 'seq nhỏ hơn luôn commit trước: ' . json_encode($res));
    // Cập nhật một đơn CŨ → xuất hiện sau con trỏ
    $oldOrder = (int)Db::val('SELECT MIN(id) FROM orders');
    t_user('operations');
    $st = Db::val('SELECT status FROM orders WHERE id = :id', ['id' => $oldOrder]);
    if ($st === 'pending') OrderService::transition($oldOrder, 'confirmed');
    $ev = SyncService::events($cursor, 100);
    $orderEvents = array_filter($ev['events'], fn($e) => $e['entity_type'] === 'order' && $e['entity_id'] === $oldOrder);
    ok(count($orderEvents) >= 1, 'đơn cũ có sự kiện mới sau con trỏ');
    $p = array_values($orderEvents)[0]['payload'];
    ok(!isset($p['ship_phone']) && !isset($p['ship_name']) && isset($p['customer_key']), 'payload không chứa tên/SĐT/địa chỉ');
    Db::exec("UPDATE settings SET value = '999999' WHERE `key` = 'sync_pruned_through'");
    Db::run("INSERT IGNORE INTO settings (`key`,`value`,updated_at) VALUES ('sync_pruned_through','999999',UTC_TIMESTAMP())");
    \App\Core\Settings::flush();
    expect_error('CURSOR_EXPIRED', fn() => SyncService::events(5, 10));
    \App\Core\Settings::set('sync_pruned_through', '0');
    return 'seq A=' . $res[0]['seq'] . ' commit trước B=' . $res[1]['seq'] . '; con trỏ hết hạn → 410 CURSOR_EXPIRED';
});

// ---------------------------------------------------------------- AT-09
check('AT-09', 'AI gửi bản nháp trong lúc giá sản phẩm thay đổi', function () {
    $key = ['id' => Db::insert('api_keys', ['name' => 't', 'key_prefix' => 'xk_test0', 'key_hash' => hash('sha256', 'x' . microtime()), 'scopes' => 'drafts:write', 'created_at' => Clock::nowDb()])];
    $p = Db::one("SELECT id, info_version FROM products WHERE slug = 'tra-gung-mat-ong'");
    $res = DraftInbox::receive($key, [[
        'client_ref' => 'faq-gung-1', 'kind' => 'faq',
        'data' => ['title' => 'Trà gừng mật ong giá bao nhiêu?', 'body' => 'Trà gừng mật ong hộp 20 túi giá 65.000đ.', 'body_is_text' => true, 'product_id' => $p['id'],
            'source_refs' => [['product_id' => (int)$p['id'], 'info_version' => (int)$p['info_version']]]],
    ]]);
    ok($res['results'][0]['status'] === 'accepted', json_encode($res));
    $cid = (int)substr($res['results'][0]['result'], 8);
    ok(Db::val('SELECT status FROM contents WHERE id = :id', ['id' => $cid]) === 'pending_review', 'bản nháp ở trạng thái chờ duyệt');
    $again = DraftInbox::receive($key, [['client_ref' => 'faq-gung-1', 'kind' => 'faq', 'data' => []]]);
    ok(!empty($again['results'][0]['duplicate']), 'gửi lại cùng client_ref không tạo trùng');
    // Giá thay đổi
    t_user('operations');
    $sku = Db::one("SELECT * FROM skus WHERE sku_code = 'TRA-GUNG-20'");
    \App\Domain\CatalogService::saveSku((int)$sku['product_id'], (int)$sku['id'], ['sku_code' => $sku['sku_code'], 'variant_label' => $sku['variant_label'], 'price' => 72000, 'net_weight_g' => $sku['net_weight_g']]);
    Db::exec('DELETE FROM flash_sale_items WHERE sku_id = :s', ['s' => $sku['id']]);
    $ans = ChatService::answer('Trà gừng mật ong giá bao nhiêu vậy shop?');
    ok($ans['source'] === 'live', 'chat lấy dữ liệu hiện hành, nguồn: ' . $ans['source']);
    ok(str_contains($ans['reply'], '72.000') && !str_contains($ans['reply'], '65.000'), 'chat dùng giá mới: ' . $ans['reply']);
    ok((int)Db::val("SELECT COUNT(*) FROM audit_logs WHERE action = 'sku.price_change'") >= 1, 'đổi giá được ghi nhật ký');
    // Bản nháp dựa trên thông tin nhãn cũ bị từ chối
    \App\Domain\CatalogService::saveProduct((int)$p['id'], array_merge(Db::one('SELECT * FROM products WHERE id = :id', ['id' => $p['id']]), ['ingredients' => 'Gừng 75%, mật ong 25%']));
    $stale = DraftInbox::receive($key, [['client_ref' => 'blog-cu-1', 'kind' => 'blog', 'data' => ['title' => 'Bài cũ', 'body' => 'x', 'body_is_text' => true, 'source_refs' => [['product_id' => (int)$p['id'], 'info_version' => (int)$p['info_version']]]]]]);
    ok($stale['results'][0]['status'] === 'rejected', 'bản nháp dựa trên nhãn cũ bị từ chối');
    return 'bản nháp chờ duyệt; chat trả 72.000 ₫ (giá hiện hành) thay vì 65.000 ₫ trong bản nháp';
});

// ---------------------------------------------------------------- AT-10
check('AT-10', 'Máy cá nhân tắt / API LLM lỗi: website vẫn bán, chat dùng FAQ hoặc kênh hỗ trợ', function () {
    // Website không có bất kỳ lời gọi nào tới Python/LLM: đặt đơn & chat chỉ dùng MySQL.
    $src = '';
    foreach (new RecursiveIteratorIterator(new RecursiveDirectoryIterator(APP_ROOT . '/src')) as $f) {
        // Đăng nhập Google/Facebook là tùy chọn và chỉ gọi khi khách chủ động đăng nhập — không thuộc luồng bán hàng
        if ($f->isFile() && !str_contains($f->getPathname(), '/Auth/OAuth.php')) $src .= file_get_contents($f->getPathname());
    }
    ok(!preg_match('/curl_init|file_get_contents\(\s*[\'"]https?:|api\.anthropic|api\.openai/i', $src), 'mã website không phụ thuộc dịch vụ ngoài');
    $faq = ChatService::answer('Phí ship được tính như thế nào?');
    ok($faq['source'] === 'faq', 'trả lời từ FAQ đã duyệt (nguồn ' . $faq['source'] . ', điểm ' . ($faq['score'] ?? '-') . ')');
    $fb = ChatService::answer('Xưởng có nhận gia công nhãn riêng cho quán không?');
    ok($fb['source'] === 'fallback' && isset($fb['support']['hotline']), 'không có câu trả lời → hiện kênh hỗ trợ');
    $sku = t_sku('T-AT10', 50000, 5);
    $q = PricingService::quote([['sku_id' => $sku, 'qty' => 1]], null, t_zone());
    $r = OrderService::create(t_input([['sku_id' => $sku, 'qty' => 1]], null, 'cod', $q['quote_token'], '0399000010'), 'sess-at10', t_key());
    ok($r['order']['code'] !== '', 'đặt đơn bình thường');
    return 'FAQ khớp (điểm ' . $faq['score'] . '), câu lạ → hotline; đơn ' . $r['order']['code'] . ' tạo bình thường';
});

// ---------------------------------------------------------------- AT-11
check('AT-11', 'Sao lưu và khôi phục sang CSDL kiểm thử', function () use ($admin, $dbName) {
    $before = [
        'products' => (int)Db::val('SELECT COUNT(*) FROM products'),
        'images' => (int)Db::val('SELECT COUNT(*) FROM product_images'),
        'orders' => (int)Db::val('SELECT COUNT(*) FROM orders'),
        'inventory' => (int)Db::val('SELECT SUM(on_hand) FROM inventory'),
        'receipts' => (int)Db::val('SELECT COUNT(*) FROM payment_receipts'),
        'history' => (int)Db::val('SELECT COUNT(*) FROM order_status_history'),
    ];
    $t0 = microtime(true);
    exec(PHP_BINARY . ' ' . escapeshellarg(BASE_ROOT . '/bin/backup.php') . ' 2>&1', $out, $code);
    ok($code === 0, 'sao lưu: ' . implode(' ', $out));
    $files = glob(config('paths.backups') . '/xuong-*.sql.gz');
    rsort($files);
    $restore = $dbName . '_restore';
    $admin->exec("DROP DATABASE IF EXISTS `$restore`; CREATE DATABASE `$restore` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci");
    $c = config('db');
    exec(sprintf('gunzip -c %s | mysql -h%s -P%d -u%s -p%s %s 2>&1', escapeshellarg($files[0]), $c['host'], $c['port'], $c['user'], escapeshellarg($c['password']), $restore), $o2, $code2);
    ok($code2 === 0, 'khôi phục: ' . implode(' ', $o2));
    $r = new PDO("mysql:host={$c['host']};port={$c['port']};dbname=$restore;charset=utf8mb4", $c['user'], $c['password']);
    $after = [
        'products' => (int)$r->query('SELECT COUNT(*) FROM products')->fetchColumn(),
        'images' => (int)$r->query('SELECT COUNT(*) FROM product_images')->fetchColumn(),
        'orders' => (int)$r->query('SELECT COUNT(*) FROM orders')->fetchColumn(),
        'inventory' => (int)$r->query('SELECT SUM(on_hand) FROM inventory')->fetchColumn(),
        'receipts' => (int)$r->query('SELECT COUNT(*) FROM payment_receipts')->fetchColumn(),
        'history' => (int)$r->query('SELECT COUNT(*) FROM order_status_history')->fetchColumn(),
    ];
    ok($before === $after, 'dữ liệu khớp: ' . json_encode([$before, $after]));
    $admin->exec("DROP DATABASE `$restore`");
    return sprintf('sao lưu + khôi phục %.1fs; danh mục, ảnh, đơn, tồn, giao dịch khớp', microtime(true) - $t0);
});

// ---------------------------------------------------------------- bổ sung
check('EX-01', 'Tác vụ hết hạn COD 48 giờ; giải phóng tồn và lượt voucher', function () {
    $sku = t_sku('T-EXP', 100000, 5);
    $vid = t_voucher('HETHAN', 10000, 0, 10);
    $q = PricingService::quote([['sku_id' => $sku, 'qty' => 2]], 'HETHAN', t_zone());
    $r = OrderService::create(t_input([['sku_id' => $sku, 'qty' => 2]], 'HETHAN', 'cod', $q['quote_token'], '0355000001'), 's-exp', t_key());
    Clock::set(Clock::now()->modify('+47 hours'));
    OrderService::expireDue();
    ok(Db::val('SELECT status FROM orders WHERE code = :c', ['c' => $r['order']['code']]) === 'pending', 'chưa tới 48 giờ');
    Clock::set(Clock::now()->modify('+2 hours'));
    OrderService::expireDue();
    ok(Db::val('SELECT status FROM orders WHERE code = :c', ['c' => $r['order']['code']]) === 'cancelled', 'quá 48 giờ bị hủy');
    ok(inv($sku)['reserved'] === 0 && (int)Db::val('SELECT reserved_count FROM vouchers WHERE id = :v', ['v' => $vid]) === 0, 'giải phóng tồn và voucher');
});

check('EX-02', 'Báo lỗi cạnh trường nhập & vùng chưa phục vụ', function () {
    $e = expect_error('VALIDATION_ERROR', fn() => OrderService::create(['items' => [['sku_id' => 1, 'qty' => 1]], 'payment_method' => 'cod', 'customer' => ['name' => 'A', 'phone' => '123', 'province' => 'Sao Hỏa', 'address' => 'x']], 's', t_key()));
    $f = $e->data['fields'];
    ok(isset($f['name'], $f['phone'], $f['province'], $f['address']), 'lỗi theo từng trường: ' . implode(',', array_keys($f)));
    $q = PricingService::quote([['sku_id' => 1, 'qty' => 1]], null, 'Sao Hỏa');
    ok($q['shipping']['served'] === false, 'vùng chưa phục vụ');
});

check('EX-03', 'Lọc HTML, VietQR CRC, tìm kiếm có dấu/không dấu, SKU', function () {
    $clean = Html::sanitize('<p onclick="x()">Chào<script>alert(1)</script><a href="javascript:alert(1)">l</a><img src=x onerror=alert(1)></p>');
    ok(!str_contains($clean, 'script') && !str_contains($clean, 'onclick') && !str_contains($clean, 'javascript') && !str_contains($clean, 'onerror'), $clean);
    ok(VietQr::crc16('123456789') === '29B1', 'CRC-16/CCITT-FALSE chuẩn');
    $p = VietQr::payload('970436', '0011001234567', 185000, 'TM251125ABCD');
    ok(str_starts_with($p, '000201010212') && str_contains($p, '5406185000') && substr($p, -4) === VietQr::crc16(substr($p, 0, -4)), 'payload EMV hợp lệ');
    $a = \App\Domain\CatalogService::search('trà gừng')['total'];
    $b = \App\Domain\CatalogService::search('tra gung')['total'];
    $c = \App\Domain\CatalogService::search('CF-ROB')['total'];
    ok($a >= 1 && $a === $b && $c >= 1, "có dấu=$a, không dấu=$b, SKU=$c");
});

check('EX-04', 'Nội dung: chờ duyệt → xuất bản; địa chỉ cố định sau khi xuất bản', function () {
    t_user('content');
    $id = ContentService::create('blog', ['title' => 'Bài viết kiểm thử', 'body' => '<p>Nội dung</p>']);
    $slug = Db::val('SELECT slug FROM contents WHERE id = :id', ['id' => $id]);
    ContentService::publish($id);
    ContentService::saveVersion($id, ['title' => 'Bài viết kiểm thử (sửa)', 'body' => '<p>Mới</p>', 'slug' => 'dia-chi-khac']);
    ok(Db::val('SELECT slug FROM contents WHERE id = :id', ['id' => $id]) === $slug, 'slug không đổi sau khi đã xuất bản');
    ok(Db::val('SELECT pub_title FROM contents WHERE id = :id', ['id' => $id]) === 'Bài viết kiểm thử', 'bản công khai giữ nguyên tới khi xuất bản lại');
    ok((int)Db::val('SELECT COUNT(*) FROM content_versions WHERE content_id = :id', ['id' => $id]) === 2, 'có lịch sử 2 phiên bản');
    t_user('warehouse');
    expect_error('FORBIDDEN', fn() => ContentService::publish($id));
});

check('EX-05', 'BM25 PHP khớp với Python (cùng điểm chuẩn hóa)', function () {
    $docs = [1 => 'phí giao hàng tính theo vùng', 2 => 'cách pha trà gừng mật ong', 3 => 'chính sách đổi trả hàng lỗi'];
    $r = Bm25::rank('phi ship tinh the nao', $docs);
    ok(array_key_first($r) === 1, 'tài liệu 1 đứng đầu: ' . json_encode($r));
    file_put_contents(sys_get_temp_dir() . '/bm25_php.json', json_enc(['query' => 'phi ship tinh the nao', 'docs' => $docs, 'scores' => $r]));
    return 'điểm=' . round($r[1], 4) . ' (đối chiếu với ai/tests)';
});

check('EX-08', 'Đăng nhập tùy chọn Google/Facebook: xác thực state/nonce/PKCE/appsecret_proof, liên kết theo email đã xác minh, đơn gắn tài khoản, xóa dữ liệu', function () {
    $GLOBALS['APP_CONFIG']['oauth'] = [];
    ok(\App\Auth\OAuth::enabledProviders() === [], 'chưa cấu hình → không bật, không hiện nút');
    expect_error('NOT_FOUND', fn() => \App\Auth\OAuth::start('google', '/'));

    $port = 8099;
    $srv = proc_open([PHP_BINARY, '-S', "127.0.0.1:$port", __DIR__ . '/fake_oauth.php'], [1 => ['file', '/dev/null', 'w'], 2 => ['file', '/dev/null', 'w']], $pipes);
    for ($i = 0; $i < 50 && !@fsockopen('127.0.0.1', $port); $i++) usleep(100000);
    $base = "http://127.0.0.1:$port";
    $GLOBALS['APP_CONFIG']['oauth'] = [
        'google' => ['client_id' => 'g-client.apps.googleusercontent.com', 'client_secret' => 'g-secret', 'auth_url' => "$base/authorize", 'token_url' => "$base/google/token"],
        'facebook' => ['client_id' => '1234567890', 'client_secret' => 'fb-test-secret', 'auth_url' => "$base/authorize", 'token_url' => "$base/fb/token", 'me_url' => "$base/fb/me"],
    ];
    try {
        $b64 = fn(string $s) => rtrim(strtr(base64_encode($s), '+/', '-_'), '=');
        // Mô phỏng một lượt đăng nhập: bắt đầu → nhà cung cấp trả code → callback
        $login = function (string $prov, array $profile, array $tamper = []) use ($b64) {
            parse_str((string)parse_url(\App\Auth\OAuth::start($prov, '/thanh-toan'), PHP_URL_QUERY), $q);
            $profile += ['nonce' => $q['nonce'] ?? null, 'challenge' => $q['code_challenge'] ?? null];
            $profile = array_merge($profile, $tamper);
            return \App\Auth\OAuth::finish($prov, ['state' => $tamper['state'] ?? $q['state'], 'code' => $b64(json_encode($profile))]);
        };
        unset($_SESSION['acct_id']);
        $p = $login('google', ['sub' => 'g-100', 'email' => 'Lan.Nguyen@Gmail.com', 'email_verified' => true, 'name' => 'Nguyễn Thị Lan']);
        ok($p['uid'] === 'g-100' && $p['email'] === 'lan.nguyen@gmail.com' && $p['email_verified'] && $p['next'] === '/thanh-toan', 'Google: id_token hợp lệ, email chuẩn hóa, quay lại trang trước');
        $acc = \App\Domain\CustomerAccountService::loginWithProfile($p);
        ok($acc === \App\Domain\CustomerAccountService::loginWithProfile($login('google', ['sub' => 'g-100', 'email' => 'lan.nguyen@gmail.com', 'email_verified' => true, 'name' => 'Lan'])), 'đăng nhập lại cùng tài khoản Google → cùng tài khoản');

        // Tấn công / lỗi: state lạ, nonce sai, PKCE sai, id_token hết hạn, sai người phát hành, appsecret_proof sai
        expect_error('OAUTH_STATE', fn() => $login('google', ['sub' => 'x'], ['state' => 'state-gia-mao']));
        parse_str((string)parse_url(\App\Auth\OAuth::start('google', '/'), PHP_URL_QUERY), $q1);
        $code = $b64(json_encode(['sub' => 'x', 'nonce' => $q1['nonce'], 'challenge' => $q1['code_challenge']]));
        \App\Auth\OAuth::finish('google', ['state' => $q1['state'], 'code' => $code]);
        expect_error('OAUTH_STATE', fn() => \App\Auth\OAuth::finish('google', ['state' => $q1['state'], 'code' => $code]));
        expect_error('OAUTH_TOKEN', fn() => $login('google', ['sub' => 'x'], ['nonce' => 'nonce-cua-phien-khac']));
        expect_error('OAUTH_TOKEN', fn() => $login('google', ['sub' => 'x'], ['challenge' => $b64(hash('sha256', 'verifier-ke-gian', true))]));
        expect_error('OAUTH_TOKEN', fn() => $login('google', ['sub' => 'x'], ['ttl' => -3600]));
        expect_error('OAUTH_TOKEN', fn() => $login('google', ['sub' => 'x'], ['iss' => 'https://evil.example']));
        expect_error('OAUTH_STATE', fn() => $login('facebook', ['sub' => 'x'], ['state' => 'abc']));
        $e = expect_error('OAUTH_DENIED', function () {
            parse_str((string)parse_url(\App\Auth\OAuth::start('facebook', '/gio-hang'), PHP_URL_QUERY), $q);
            \App\Auth\OAuth::finish('facebook', ['state' => $q['state'], 'error' => 'access_denied']);
        });
        ok(($e->data['next'] ?? '') === '/gio-hang', 'khách bấm Hủy → báo hủy, giữ trang quay lại');
        $GLOBALS['APP_CONFIG']['oauth']['facebook']['client_secret'] = 'sai';
        expect_error('OAUTH_TOKEN', fn() => $login('facebook', ['sub' => 'fb-1']));
        $GLOBALS['APP_CONFIG']['oauth']['facebook']['client_secret'] = 'fb-test-secret';
        ok(\App\Auth\OAuth::safeNext('//evil.example/x') === '/tai-khoan' && \App\Auth\OAuth::safeNext('https://evil.example') === '/tai-khoan' && \App\Auth\OAuth::safeNext('/\\evil.example') === '/tai-khoan', 'chặn chuyển hướng mở ra ngoài');

        // Facebook cùng email đã xác minh → gộp vào tài khoản Google; email chưa xác minh → tài khoản riêng
        $fb = $login('facebook', ['sub' => 'fb-200', 'email' => 'lan.nguyen@gmail.com', 'name' => 'Lan Nguyen']);
        ok($fb['uid'] === 'fb-200' && \App\Domain\CustomerAccountService::loginWithProfile($fb) === $acc, 'Facebook (appsecret_proof) cùng email đã xác minh → cùng tài khoản');
        $other = \App\Domain\CustomerAccountService::loginWithProfile($login('google', ['sub' => 'g-999', 'email' => 'lan.nguyen@gmail.com', 'email_verified' => false, 'name' => 'Kẻ mạo danh']));
        ok($other !== $acc, 'email CHƯA xác minh không được gộp vào tài khoản có sẵn');
        $noMail = \App\Domain\CustomerAccountService::loginWithProfile($login('facebook', ['sub' => 'fb-300', 'name' => 'Không Email']));
        ok($noMail !== $acc && Db::val('SELECT email FROM customer_accounts WHERE id = :id', ['id' => $noMail]) === null, 'Facebook không cấp email vẫn đăng nhập được');

        // Đơn đặt khi đăng nhập gắn tài khoản; đơn khách lẻ cùng SĐT KHÔNG hiện trong tài khoản
        $sku = t_sku('ACC-1', 50000, 20);
        $q = PricingService::quote([['sku_id' => $sku, 'qty' => 1]], null, t_zone());
        $guest = OrderService::create(t_input([['sku_id' => $sku, 'qty' => 1]], null, 'cod', $q['quote_token'], '0987000111'), 'sess-acc-guest', t_key());
        $q2 = PricingService::quote([['sku_id' => $sku, 'qty' => 2]], null, t_zone());
        $in = t_input([['sku_id' => $sku, 'qty' => 2]], null, 'cod', $q2['quote_token'], '0987000111');
        $in['marketing_consent'] = false;
        $mine = OrderService::create($in, 'sess-acc', t_key(), $acc);
        $list = \App\Domain\CustomerAccountService::orders($acc);
        ok(count($list) === 1 && $list[0]['code'] === $mine['order']['code'] && $list[0]['code'] !== $guest['order']['code'], 'tài khoản chỉ thấy đơn đặt khi đăng nhập');
        $a = Db::one('SELECT * FROM customer_accounts WHERE id = :id', ['id' => $acc]);
        ok($a['ship_phone'] === '0987000111' && $a['ship_province'] === t_zone(), 'ghi nhớ địa chỉ giao hàng gần nhất để điền sẵn');
        ok(\App\Domain\CustomerAccountService::marketingConsent($acc) === false, 'trạng thái nhận tin theo đơn');
        \App\Domain\CustomerAccountService::setMarketingConsent($acc, true);
        ok(\App\Domain\CustomerAccountService::marketingConsent($acc) === true, 'khách tự bật nhận tin trên trang tài khoản');
        \App\Domain\CustomerAccountService::setMarketingConsent($acc, false);
        ok((int)Db::val("SELECT COUNT(*) FROM audit_logs WHERE action = 'consent.withdrawn' AND entity_id = :a", ['a' => (string)$acc]) === 1, 'rút đồng ý có nhật ký');

        // Callback xóa dữ liệu của Facebook: chữ ký sai bị từ chối; tài khoản còn Google → chỉ gỡ Facebook
        $signed = function (array $payload, string $secret = 'fb-test-secret') use ($b64) {
            $p = $b64(json_encode($payload));
            return $b64(hash_hmac('sha256', $p, $secret, true)) . '.' . $p;
        };
        ok(\App\Auth\OAuth::parseSignedRequest($signed(['algorithm' => 'HMAC-SHA256', 'user_id' => 'fb-200'], 'khoa-gia')) === null, 'signed_request sai chữ ký bị từ chối');
        $req = \App\Auth\OAuth::parseSignedRequest($signed(['algorithm' => 'HMAC-SHA256', 'user_id' => 'fb-200', 'issued_at' => time()]));
        $code1 = \App\Domain\CustomerAccountService::deleteByFacebook((string)$req['user_id']);
        ok(strlen($code1) === 16 && (int)Db::val('SELECT COUNT(*) FROM account_identities WHERE account_id = :a', ['a' => $acc]) === 1 && Db::val('SELECT 1 FROM customer_accounts WHERE id = :a', ['a' => $acc]), 'còn đăng nhập Google → chỉ xóa liên kết Facebook');
        $code2 = \App\Domain\CustomerAccountService::deleteByFacebook('fb-300');
        ok(!Db::val('SELECT 1 FROM customer_accounts WHERE id = :a', ['a' => $noMail]) && Db::val('SELECT status FROM account_deletions WHERE confirmation_code = :c', ['c' => $code2]) === 'completed', 'tài khoản chỉ có Facebook → xóa hẳn, có mã tra cứu');
        ok(Db::val('SELECT status FROM account_deletions WHERE confirmation_code = :c', ['c' => \App\Domain\CustomerAccountService::deleteByFacebook('fb-khong-co')]) === 'not_found', 'người chưa từng đăng nhập → ghi nhận không có dữ liệu');

        // Khách tự xóa tài khoản: đơn giữ lại (kế toán) nhưng bỏ liên kết
        $code3 = \App\Domain\CustomerAccountService::delete($acc);
        ok(!Db::val('SELECT 1 FROM customer_accounts WHERE id = :a', ['a' => $acc]) && (int)Db::val('SELECT COUNT(*) FROM account_identities WHERE account_id = :a', ['a' => $acc]) === 0, 'xóa tài khoản và danh tính đăng nhập');
        ok(Db::val('SELECT account_id FROM orders WHERE code = :c', ['c' => $mine['order']['code']]) === null && Db::val('SELECT status FROM account_deletions WHERE confirmation_code = :c', ['c' => $code3]) === 'completed', 'đơn vẫn còn nhưng không gắn tài khoản');
    } finally {
        proc_terminate($srv);
        proc_close($srv);
    }
    return 'state dùng một lần, nonce/PKCE/hạn/issuer, appsecret_proof; email chưa xác minh không gộp; đơn khách lẻ không lộ; xóa theo yêu cầu Facebook có mã tra cứu';
});

check('EX-07', 'Trang Chính sách bảo mật thông tin & Điều khoản sử dụng: có sẵn, chèn cấu hình an toàn, không ghi đè trang đã sửa', function () {
    ok((int)Db::val("SELECT COUNT(*) FROM schema_migrations WHERE version = '004_legal_pages'") === 1, 'migration PHP 004 đã chạy');
    foreach (['bao-mat' => 'Chính sách bảo mật thông tin', 'dieu-khoan-su-dung' => 'Điều khoản sử dụng'] as $slug => $title) {
        $c = Db::one("SELECT * FROM contents WHERE kind = 'page' AND slug = :s", ['s' => $slug]);
        ok($c && $c['status'] === 'published' && $c['pub_title'] === $title, "$slug đã xuất bản với tiêu đề \"$title\" (seed không ghi đè)");
    }
    $render = fn(string $slug) => (new \App\Http\StoreController())->page($slug);
    \App\Core\Settings::set('representative', '');
    $html = $render('dieu-khoan-su-dung');
    ok(str_contains($html, '<h1 class="text-3xl">Điều khoản sử dụng</h1>') && str_contains($html, 'Có hiệu lực từ') && str_contains($html, 'aria-label="Mục lục"'), 'có tiêu đề, ngày hiệu lực, mục lục');
    ok(str_contains($html, 'trong 24 giờ') && str_contains($html, '[chưa cập nhật: người đại diện]') && !str_contains($html, '{{'), 'biến cấu hình được chèn; mục trống hiện nhãn [chưa cập nhật]');
    \App\Core\Settings::set('representative', '<script>alert(1)</script>Nguyễn Văn A');
    $html = $render('dieu-khoan-su-dung');
    ok(str_contains($html, '&lt;script&gt;alert(1)&lt;/script&gt;Nguyễn Văn A') && !str_contains($html, '<script>alert(1)'), 'giá trị cấu hình được mã hóa HTML (chống XSS)');
    ok(str_contains($html, 'href="/chinh-sach/dieu-khoan-su-dung"') && str_contains($html, 'href="/chinh-sach/bao-mat"'), 'chân trang có liên kết hai trang');
    ok(str_contains($render('bao-mat'), 'data-clear-local'), 'trang bảo mật có nút xóa thông tin lưu trên trình duyệt');
    ok(str_contains(\App\Core\View::partial('store/checkout', ['provinces' => []]), '/chinh-sach/dieu-khoan-su-dung'), 'trang thanh toán dẫn tới Điều khoản sử dụng');
    ok(\App\Domain\LegalPages::install() === ['bao-mat' => 'unchanged', 'dieu-khoan-su-dung' => 'unchanged'], 'chạy lại migration không tạo phiên bản thừa');
    // Xưởng tự sửa điều khoản → bản cập nhật kèm mã nguồn chỉ vào chờ duyệt
    t_user('content');
    $id = (int)Db::val("SELECT id FROM contents WHERE slug = 'dieu-khoan-su-dung'");
    ContentService::saveVersion($id, ['title' => 'Điều khoản sử dụng', 'body' => '<p>Bản xưởng tự sửa</p>']);
    ContentService::publish($id);
    $r = \App\Domain\LegalPages::install();
    ok($r['dieu-khoan-su-dung'] === 'new_version_pending' && Db::val('SELECT pub_body FROM contents WHERE id = :id', ['id' => $id]) === '<p>Bản xưởng tự sửa</p>', 'không ghi đè bản xưởng đã sửa, thêm phiên bản chờ duyệt');
    // Trang bảo mật còn là bản mẫu cũ → được thay bằng nội dung đầy đủ
    $bid = (int)Db::val("SELECT id FROM contents WHERE slug = 'bao-mat'");
    Db::exec('UPDATE content_versions SET body = :b WHERE content_id = :c', ['b' => '<p>cũ</p><p><em>Bản mẫu — xưởng cần rà soát và xác nhận.</em></p>', 'c' => $bid]);
    Db::exec("UPDATE contents SET pub_body = '<p>cũ</p>' WHERE id = :id", ['id' => $bid]);
    ok(\App\Domain\LegalPages::install()['bao-mat'] === 'updated' && str_contains((string)Db::val('SELECT pub_body FROM contents WHERE id = :id', ['id' => $bid]), 'Luật Bảo vệ dữ liệu cá nhân'), 'bản mẫu cũ được thay bằng chính sách đầy đủ');
    return 'hai trang xuất bản; biến cấu hình mã hóa an toàn; trang đã sửa được giữ nguyên';
});

check('EX-06', 'Làm mới dữ liệu trước khi chạy thật: sao lưu, xóa dữ liệu thử, giữ cấu hình; Python phải tải lại', function () {
    $adminId = t_user('admin');
    \App\Core\Settings::set('store_name', 'Xưởng Kiểm Thử');
    $oldCursor = (int)Db::val('SELECT last_seq FROM sync_counter WHERE id = 1') - 3;
    $cats = (int)Db::val('SELECT COUNT(*) FROM categories');
    $zones = (int)Db::val('SELECT COUNT(*) FROM shipping_zones');
    $pages = (int)Db::val("SELECT COUNT(*) FROM contents WHERE kind = 'page'");
    $sku = (int)Db::val("SELECT id FROM skus WHERE sku_code = 'NC-25H-500'");
    $onHand = inv($sku)['on_hand'];
    ok((int)Db::val('SELECT COUNT(*) FROM orders') > 0, 'có đơn thử');
    \App\Domain\CustomerAccountService::loginWithProfile(['provider' => 'google', 'uid' => 'g-reset', 'email' => 'thu@gmail.com', 'email_verified' => true, 'name' => 'Khách thử']);
    $r = \App\Domain\DataResetService::run(['demo_users' => true, 'logs' => true], $adminId);
    ok(is_file($r['backup']['file']), 'đã sao lưu trước khi xóa');
    foreach (['orders', 'customers', 'customer_accounts', 'account_identities', 'payment_receipts', 'refunds', 'payment_discrepancies', 'voucher_usages', 'idempotency_keys', 'care_suggestions'] as $t) {
        ok((int)Db::val("SELECT COUNT(*) FROM $t") === 0, "$t trống");
    }
    ok((int)Db::val('SELECT SUM(reserved) FROM inventory') === 0 && (int)Db::val('SELECT SUM(used_count + reserved_count) FROM vouchers') === 0, 'tồn giữ và lượt voucher về 0');
    ok(inv($sku)['on_hand'] === $onHand, 'giữ tồn thực tế khi không chọn đặt về 0');
    \App\Core\Settings::flush();
    ok(setting('store_name') === 'Xưởng Kiểm Thử' && (int)Db::val('SELECT COUNT(*) FROM categories') === $cats && (int)Db::val('SELECT COUNT(*) FROM shipping_zones') === $zones && (int)Db::val("SELECT COUNT(*) FROM contents WHERE kind = 'page'") === $pages, 'giữ cấu hình, danh mục, vùng giao, trang chính sách');
    ok((int)Db::val('SELECT COUNT(*) FROM users WHERE id = :id', ['id' => $adminId]) === 1 && (int)Db::val("SELECT COUNT(*) FROM users WHERE email LIKE '%@xuong.local' AND id <> :id", ['id' => $adminId]) === 0, 'xóa tài khoản mẫu, giữ người thao tác');
    expect_error('CURSOR_EXPIRED', fn() => SyncService::events($oldCursor, 10));
    $snap = SyncService::snapshot(0, 10);
    ok($snap['orders'] === [] && SyncService::events($snap['as_of_seq'], 10)['events'] === [], 'Python tải lại bản chụp rỗng rồi đồng bộ tiếp bình thường');
    ok((int)Db::val("SELECT COUNT(*) FROM audit_logs WHERE action = 'data.reset'") === 1, 'ghi nhật ký thao tác làm mới');
    Auth::actAs(null);
    $q = PricingService::quote([['sku_id' => $sku, 'qty' => 1]], null, t_zone());
    $o = OrderService::create(t_input([['sku_id' => $sku, 'qty' => 1]], null, 'cod', $q['quote_token']), 'sess-after-reset', t_key());
    ok($o['order']['code'] !== '' && (int)Db::val('SELECT COUNT(*) FROM orders') === 1, 'bán hàng bình thường sau khi làm mới');
    t_user('operations');
    expect_error('FORBIDDEN', fn() => Auth::require('data.reset'));
    $r2 = \App\Domain\DataResetService::run(['products' => true, 'promotions' => true, 'content' => true], null);
    ok((int)Db::val('SELECT COUNT(*) FROM products') === 0 && (int)Db::val('SELECT COUNT(*) FROM vouchers') === 0 && (int)Db::val("SELECT COUNT(*) FROM contents WHERE kind IN ('blog','faq')") === 0 && (int)Db::val('SELECT COUNT(*) FROM categories') === $cats, 'xóa sạch dữ liệu mẫu, vẫn giữ danh mục');
    return 'sao lưu ' . basename($r['backup']['file']) . '; xóa ' . array_sum($r['deleted']) . ' bản ghi thử; cấu hình giữ nguyên; nhân viên vận hành không có quyền';
});

// ---------------------------------------------------------------- báo cáo
$pass = count(array_filter($GLOBALS['T_RESULTS'], fn($r) => $r[2] === 'ĐẠT'));
$total = count($GLOBALS['T_RESULTS']);
echo "\nKết quả: $pass/$total ca đạt\n";

foreach ($argv as $a) {
    if (str_starts_with($a, '--report=')) {
        $file = substr($a, 9);
        $md = "# Kết quả nghiệm thu tự động\n\n";
        $md .= "- Thời điểm chạy: " . vn_time(Clock::nowDb(), 'd/m/Y H:i') . " (giờ Việt Nam)\n";
        $md .= "- Môi trường: PHP " . PHP_VERSION . ", " . Db::val('SELECT VERSION()') . "\n";
        $md .= "- Lệnh: `XUONG_DB=xuong_test php tests/acceptance.php`\n";
        $md .= "- Tổng: **$pass/$total ca đạt**\n\n";
        $md .= "| Mã | Kịch bản | Kết quả | Ghi chú | ms |\n|---|---|---|---|---|\n";
        foreach ($GLOBALS['T_RESULTS'] as [$id, $name, $st, $note, $ms]) {
            $md .= "| $id | " . str_replace('|', '/', $name) . " | **$st** | " . str_replace(['|', "\n"], ['/', ' '], $note) . " | $ms |\n";
        }
        $md .= "\nAT-08 phía Python (mất kết nối, lô có sự kiện trùng, cập nhật đơn cũ) chạy bằng `pytest` trong thư mục `ai/` — xem `ai/tests/test_sync.py`.\n";
        @mkdir(dirname($file), 0755, true);
        file_put_contents($file, $md);
        echo "Đã ghi báo cáo: $file\n";
    }
}
exit($pass === $total ? 0 : 1);
