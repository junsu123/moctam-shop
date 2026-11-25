<?php
declare(strict_types=1);

namespace App\Domain;

use App\Core\ApiError;
use App\Core\Audit;
use App\Core\Auth;
use App\Core\Clock;
use App\Core\Db;
use App\Core\Settings;
use App\Core\Text;
use App\Core\Ulid;

/**
 * Tạo đơn (FR-04, §4.1) và luồng trạng thái (FR-05, §4.2).
 */
final class OrderService
{
    public const STATUS_LABELS = [
        'pending'   => 'Chờ xác nhận',
        'confirmed' => 'Đã xác nhận',
        'shipping'  => 'Đang giao',
        'delivered' => 'Đã giao',
        'cancelled' => 'Đã hủy',
        'returning' => 'Đang hoàn hàng',
        'returned'  => 'Đã hoàn hàng',
    ];

    public const PAYMENT_LABELS = [
        'unpaid' => 'Chưa thu', 'partial' => 'Thu thiếu', 'paid' => 'Đã thu đủ', 'overpaid' => 'Thu thừa',
        'partially_refunded' => 'Hoàn một phần', 'refunded' => 'Đã hoàn tiền',
    ];

    /** Bảng chuyển trạng thái hợp lệ → quyền cần có. */
    public const TRANSITIONS = [
        'pending>confirmed'   => 'orders.process',
        'confirmed>shipping'  => 'orders.process',
        'shipping>delivered'  => 'orders.process',
        'pending>cancelled'   => 'orders.process',
        'confirmed>cancelled' => 'orders.process',
        'shipping>returning'  => 'orders.return',
        'delivered>returning' => 'orders.return',
        'returning>returned'  => 'orders.return',
    ];

    // ================================================================== TẠO ĐƠN

    /**
     * @param array $input {items, voucher_code, customer{name,phone,province,address,note}, payment_method, marketing_consent, quote_token}
     * @return array {order, replayed}
     */
    public static function create(array $input, string $sessionId, string $idemKey, ?int $accountId = null): array
    {
        if (!preg_match('/^[A-Za-z0-9_\-]{16,80}$/', $idemKey)) {
            throw new ApiError('IDEMPOTENCY_KEY_REQUIRED', 'Thiếu hoặc sai định dạng Idempotency-Key.', 400);
        }
        $clean = self::validate($input);
        $sessionHash = hash('sha256', $sessionId);
        $requestHash = hash('sha256', json_enc([
            $clean['items'], $clean['voucher_code'], $clean['customer'], $clean['payment_method'], $clean['marketing_consent'],
        ]));

        // Gửi lại sau khi đã tạo đơn → trả đơn ban đầu (AT-03).
        if ($existing = self::replay($idemKey, $sessionHash, $requestHash)) {
            return $existing;
        }

        try {
            $orderId = Db::tx(function () use ($clean, $input, $idemKey, $sessionHash, $requestHash, $accountId) {
                $now = Clock::nowDb();
                // Chiếm khóa trước: yêu cầu trùng đồng thời sẽ chờ ở đây rồi nhận lỗi trùng khóa.
                Db::insert('idempotency_keys', [
                    'id_key' => $idemKey, 'session_hash' => $sessionHash, 'request_hash' => $requestHash,
                    'order_id' => null, 'created_at' => $now,
                ]);

                $quote = PricingService::quote(
                    array_map(fn($s, $q) => ['sku_id' => $s, 'qty' => $q], array_keys($clean['items']), $clean['items']),
                    $clean['voucher_code'],
                    $clean['customer']['province']
                );
                self::assertQuoteStillValid($quote, $input['quote_token'] ?? null);

                $c = $clean['customer'];
                $customerId = self::upsertCustomer($c['name'], $c['phone'], $clean['marketing_consent']);
                $holdHours = $clean['payment_method'] === 'vietqr' ? Settings::int('hold_hours_vietqr', 24) : Settings::int('hold_hours_cod', 48);
                $code = self::newCode();
                $orderId = Db::insert('orders', [
                    'code'             => $code,
                    'access_token'     => bin2hex(random_bytes(16)),
                    'customer_id'      => $customerId,
                    'account_id'       => $accountId,
                    'status'           => 'pending',
                    'payment_method'   => $clean['payment_method'],
                    'payment_status'   => 'unpaid',
                    'ship_name'        => $c['name'],
                    'ship_phone'       => $c['phone'],
                    'ship_province'    => $c['province'],
                    'ship_address'     => $c['address'],
                    'ship_note'        => $c['note'] ?: null,
                    'zone_id'          => $quote['shipping']['zone_id'],
                    'zone_name'        => $quote['shipping']['zone_name'],
                    'shipping_rate_id' => $quote['shipping']['rate_id'],
                    'goods_subtotal'   => $quote['goods_subtotal'],
                    'voucher_id'       => ($quote['voucher']['valid'] ?? false) ? $quote['voucher']['voucher_id'] : null,
                    'voucher_code'     => ($quote['voucher']['valid'] ?? false) ? $quote['voucher']['code'] : null,
                    'voucher_discount' => $quote['discount'],
                    'shipping_fee'     => $quote['shipping']['fee'],
                    'total'            => $quote['total'],
                    'transfer_content' => $code,
                    'expires_at'       => Clock::db(Clock::now()->modify("+{$holdHours} hours")),
                    'created_at'       => $now,
                    'updated_at'       => $now,
                ]);

                // Dòng hàng + giữ tồn (sắp theo sku_id để tránh deadlock)
                $lines = $quote['lines'];
                usort($lines, fn($a, $b) => $a['sku_id'] <=> $b['sku_id']);
                foreach ($lines as $l) {
                    Db::insert('order_items', [
                        'order_id' => $orderId, 'sku_id' => $l['sku_id'], 'product_id' => $l['product_id'],
                        'category_id' => $l['category_id'], 'product_name' => $l['product_name'],
                        'sku_code' => $l['sku_code'], 'variant_label' => $l['variant_label'],
                        'list_price' => $l['list_price'], 'unit_price' => $l['unit_price'],
                        'flash_sale_id' => $l['flash_sale_id'], 'quantity' => $l['qty'],
                        'line_total' => $l['line_total'], 'voucher_eligible' => $l['voucher_eligible'] ? 1 : 0,
                    ]);
                    if (!InventoryService::reserve($l['sku_id'], $l['qty'], $orderId, "order:$orderId:new>pending")) {
                        throw new RaceLost('stock');
                    }
                }

                // Giữ lượt voucher (UPDATE có điều kiện — AT-04)
                if ($quote['voucher']['valid'] ?? false) {
                    $ok = Db::exec(
                        'UPDATE vouchers SET reserved_count = reserved_count + 1, updated_at = :t
                          WHERE id = :id AND is_active = 1 AND starts_at <= :n AND ends_at > :n2
                            AND (usage_limit IS NULL OR reserved_count + used_count < usage_limit)',
                        ['id' => $quote['voucher']['voucher_id'], 't' => $now, 'n' => $now, 'n2' => $now]
                    );
                    if ($ok !== 1) {
                        throw new RaceLost('voucher');
                    }
                    Db::insert('voucher_usages', [
                        'voucher_id' => $quote['voucher']['voucher_id'], 'order_id' => $orderId,
                        'amount' => $quote['discount'], 'status' => 'reserved', 'created_at' => $now, 'updated_at' => $now,
                    ]);
                }

                Db::insert('order_status_history', [
                    'order_id' => $orderId, 'from_status' => null, 'to_status' => 'pending',
                    'actor_type' => 'customer', 'reason' => 'Khách đặt hàng (' . strtoupper($clean['payment_method']) . ')', 'created_at' => $now,
                ]);
                Db::exec('UPDATE idempotency_keys SET order_id = :o WHERE id_key = :k', ['o' => $orderId, 'k' => $idemKey]);
                if ($accountId) {
                    CustomerAccountService::rememberShipping($accountId, $c);
                }
                SyncService::emitOrder($orderId, 'order.created');
                return $orderId;
            });
        } catch (RaceLost $e) {
            // Thua tranh chấp tồn/voucher: giao dịch đã hoàn tác toàn bộ. Báo giá lại với dữ liệu mới nhất.
            $fresh = PricingService::quote(
                array_map(fn($s, $q) => ['sku_id' => $s, 'qty' => $q], array_keys($clean['items']), $clean['items']),
                $clean['voucher_code'], $clean['customer']['province']
            );
            if ($e->getMessage() === 'stock') {
                throw new ApiError('OUT_OF_STOCK', 'Rất tiếc, một số sản phẩm vừa hết hoặc không đủ số lượng.', 409, ['issues' => $fresh['issues'], 'quote' => $fresh]);
            }
            throw new ApiError('QUOTE_CHANGED', 'Mã giảm giá vừa hết lượt. Vui lòng xem lại tổng tiền trước khi đặt.', 409, ['quote' => $fresh]);
        } catch (\PDOException $e) {
            if (Db::isDuplicate($e, 'PRIMARY') && ($existing = self::replay($idemKey, $sessionHash, $requestHash))) {
                return $existing;
            }
            Audit::error('order', 'CREATE_FAILED', $e->getMessage());
            throw $e;
        } catch (ApiError $e) {
            if (!in_array($e->errorCode, ['QUOTE_CHANGED', 'OUT_OF_STOCK', 'VALIDATION_ERROR'], true)) {
                Audit::error('order', $e->errorCode, $e->getMessage());
            }
            throw $e;
        }

        return ['order' => self::publicSummary($orderId), 'replayed' => false];
    }

    private static function replay(string $idemKey, string $sessionHash, string $requestHash): ?array
    {
        $row = Db::one('SELECT * FROM idempotency_keys WHERE id_key = :k', ['k' => $idemKey]);
        if (!$row || $row['order_id'] === null) {
            return null;
        }
        if (!hash_equals($row['session_hash'], $sessionHash) || !hash_equals($row['request_hash'], $requestHash)) {
            throw new ApiError('IDEMPOTENCY_CONFLICT', 'Yêu cầu trùng khóa nhưng khác nội dung. Vui lòng tải lại trang.', 409);
        }
        return ['order' => self::publicSummary((int)$row['order_id']), 'replayed' => true];
    }

    private static function assertQuoteStillValid(array $quote, ?string $token): void
    {
        if (!$quote['shipping']['served']) {
            throw new ApiError('ZONE_NOT_SERVED', 'Rất tiếc, khu vực này chưa được phục vụ.', 422, ['quote' => $quote]);
        }
        if ($quote['issues']) {
            throw new ApiError('OUT_OF_STOCK', 'Một số sản phẩm đã hết hoặc không đủ số lượng.', 409, ['issues' => $quote['issues'], 'quote' => $quote]);
        }
        if (!$quote['lines']) {
            throw ApiError::validation(['items' => 'Giỏ hàng trống.']);
        }
        $t = PricingService::verifyToken($token);
        if (!$t || $t['expires'] < Clock::now()->getTimestamp() || !hash_equals($t['fingerprint'], $quote['fingerprint'])) {
            throw new ApiError('QUOTE_CHANGED', 'Giá hoặc ưu đãi đã thay đổi (hoặc báo giá hết hạn). Vui lòng xem lại tổng tiền và xác nhận.', 409, ['quote' => $quote]);
        }
    }

    public static function validate(array $in): array
    {
        $errors = [];
        $c = is_array($in['customer'] ?? null) ? $in['customer'] : [];
        $name = trim((string)($c['name'] ?? ''));
        $phone = Text::normalizePhone((string)($c['phone'] ?? ''));
        $province = trim((string)($c['province'] ?? ''));
        $address = trim((string)($c['address'] ?? ''));
        $note = trim((string)($c['note'] ?? ''));
        $method = (string)($in['payment_method'] ?? '');

        if (mb_strlen($name) < 2 || mb_strlen($name) > 120) $errors['name'] = 'Vui lòng nhập họ tên (2–120 ký tự).';
        if ($phone === null) $errors['phone'] = 'Số điện thoại di động Việt Nam chưa đúng (VD: 0912345678).';
        if ($province === '') $errors['province'] = 'Vui lòng chọn tỉnh/thành.';
        elseif (!ShippingService::zoneFor($province)) $errors['province'] = 'Khu vực này chưa được phục vụ.';
        if (mb_strlen($address) < 6 || mb_strlen($address) > 400) $errors['address'] = 'Vui lòng nhập địa chỉ chi tiết (số nhà, đường, phường/xã).';
        if (mb_strlen($note) > 400) $errors['note'] = 'Ghi chú tối đa 400 ký tự.';
        if (!in_array($method, ['cod', 'vietqr'], true)) $errors['payment_method'] = 'Vui lòng chọn phương thức thanh toán.';

        $items = [];
        try {
            $items = PricingService::normalizeItems(is_array($in['items'] ?? null) ? $in['items'] : []);
        } catch (ApiError $e) {
            $errors += $e->data['fields'] ?? [];
        }
        if (!$items) $errors['items'] = 'Giỏ hàng trống.';
        if ($errors) {
            throw ApiError::validation($errors);
        }
        return [
            'items'             => $items,
            'voucher_code'      => strtoupper(trim((string)($in['voucher_code'] ?? ''))) ?: null,
            'customer'          => ['name' => $name, 'phone' => $phone, 'province' => $province, 'address' => $address, 'note' => $note],
            'payment_method'    => $method,
            'marketing_consent' => !empty($in['marketing_consent']),
        ];
    }

    private static function upsertCustomer(string $name, string $phone, bool $consent): int
    {
        $now = Clock::nowDb();
        $existing = Db::one('SELECT id, marketing_consent FROM customers WHERE phone = :p FOR UPDATE', ['p' => $phone]);
        if ($existing) {
            $data = ['full_name' => $name, 'updated_at' => $now];
            if ((bool)$existing['marketing_consent'] !== $consent) {
                $data['marketing_consent'] = $consent ? 1 : 0;
                $data['consent_updated_at'] = $now;
            }
            Db::update('customers', $data, 'id = :id', ['id' => $existing['id']]);
            return (int)$existing['id'];
        }
        return Db::insert('customers', [
            'phone' => $phone, 'full_name' => $name,
            'customer_key' => substr(hash_hmac('sha256', $phone, (string)config('app_key')), 0, 24),
            'marketing_consent' => $consent ? 1 : 0, 'consent_updated_at' => $consent ? $now : null,
            'created_at' => $now, 'updated_at' => $now,
        ]);
    }

    private static function newCode(): string
    {
        $prefix = preg_replace('/[^A-Z]/', '', strtoupper(Settings::get('order_code_prefix', 'TM'))) ?: 'TM';
        for ($i = 0; $i < 8; $i++) {
            $code = $prefix . Clock::toLocal(Clock::nowDb())->format('ymd') . Ulid::code(4);
            if (!Db::val('SELECT 1 FROM orders WHERE code = :c', ['c' => $code])) {
                return $code;
            }
        }
        throw new \RuntimeException('Không tạo được mã đơn');
    }

    /** Thông tin trả về cho khách sau khi đặt (trang xác nhận). */
    public static function publicSummary(int $orderId): array
    {
        $o = Db::one('SELECT * FROM orders WHERE id = :id', ['id' => $orderId]);
        $items = Db::all('SELECT product_name, variant_label, sku_code, unit_price, list_price, quantity, line_total FROM order_items WHERE order_id = :id ORDER BY id', ['id' => $orderId]);
        $out = [
            'code' => $o['code'], 'access_token' => $o['access_token'], 'status' => $o['status'],
            'status_label' => self::STATUS_LABELS[$o['status']], 'payment_method' => $o['payment_method'],
            'payment_status' => $o['payment_status'], 'goods_subtotal' => (int)$o['goods_subtotal'],
            'voucher_code' => $o['voucher_code'], 'voucher_discount' => (int)$o['voucher_discount'],
            'shipping_fee' => (int)$o['shipping_fee'], 'total' => (int)$o['total'], 'expires_at' => $o['expires_at'],
            'created_at' => $o['created_at'], 'items' => $items,
            'ship' => ['name' => $o['ship_name'], 'phone' => $o['ship_phone'], 'province' => $o['ship_province'], 'address' => $o['ship_address']],
            'confirm_url' => '/don-hang/' . $o['code'] . '?t=' . $o['access_token'],
        ];
        if ($o['payment_method'] === 'vietqr') {
            $out['vietqr'] = VietQr::instructions((int)$o['total'], $o['transfer_content']);
        }
        return $out;
    }

    // ================================================================== TRẠNG THÁI

    /**
     * Chuyển trạng thái có kiểm tra quyền, khóa hàng và ghi biến động kho đúng một lần.
     * $actor: 'user' (mặc định, cần quyền) | 'system' (tác vụ hết hạn)
     */
    public static function transition(int $orderId, string $to, ?string $reason = null, array $extra = [], string $actor = 'user'): array
    {
        return Db::tx(function () use ($orderId, $to, $reason, $extra, $actor) {
            $o = Db::one('SELECT * FROM orders WHERE id = :id FOR UPDATE', ['id' => $orderId]);
            if (!$o) {
                throw ApiError::notFound('Không tìm thấy đơn hàng.');
            }
            $from = $o['status'];
            $key = "$from>$to";
            if (!isset(self::TRANSITIONS[$key])) {
                throw new ApiError('INVALID_TRANSITION', sprintf('Không thể chuyển đơn từ "%s" sang "%s".', self::STATUS_LABELS[$from] ?? $from, self::STATUS_LABELS[$to] ?? $to), 409);
            }
            if ($actor === 'user') {
                Auth::require(self::TRANSITIONS[$key]);
            }
            $reason = $reason !== null ? trim($reason) : null;
            $now = Clock::nowDb();
            $tk = "order:$orderId:$key";
            $items = Db::all('SELECT * FROM order_items WHERE order_id = :id ORDER BY sku_id', ['id' => $orderId]);
            $update = ['status' => $to, 'updated_at' => $now];

            switch ($key) {
                case 'pending>confirmed':
                    if ($o['payment_method'] === 'vietqr') {
                        $open = (int)Db::val("SELECT COUNT(*) FROM payment_discrepancies WHERE order_id = :id AND status = 'open'", ['id' => $orderId]);
                        if ((int)$o['amount_received'] < (int)$o['total']) {
                            throw new ApiError('PAYMENT_NOT_RECONCILED', 'Đơn VietQR chưa được đối soát đủ tiền (' . money($o['amount_received']) . ' / ' . money($o['total']) . ').', 409);
                        }
                        if ($open > 0) {
                            throw new ApiError('DISCREPANCY_OPEN', 'Đơn còn sai lệch thanh toán chưa xử lý.', 409);
                        }
                    }
                    $update['needs_review'] = 0;
                    break;

                case 'confirmed>shipping':
                    foreach ($items as $it) {
                        InventoryService::ship((int)$it['sku_id'], (int)$it['quantity'], $orderId, $tk);
                    }
                    self::voucherUsage($orderId, 'reserved', 'used');
                    if (!empty($extra['carrier_name'])) $update['carrier_name'] = mb_substr(trim($extra['carrier_name']), 0, 80);
                    if (!empty($extra['tracking_code'])) $update['tracking_code'] = mb_substr(trim($extra['tracking_code']), 0, 80);
                    break;

                case 'shipping>delivered':
                    $update['delivered_at'] = $now;
                    break;

                case 'pending>cancelled':
                case 'confirmed>cancelled':
                    if ($reason === null || $reason === '') {
                        throw ApiError::validation(['reason' => 'Vui lòng ghi lý do hủy.']);
                    }
                    foreach ($items as $it) {
                        InventoryService::release((int)$it['sku_id'], (int)$it['quantity'], $orderId, $tk, $reason);
                    }
                    self::voucherUsage($orderId, 'reserved', 'released');
                    $update['needs_review'] = 0;
                    $net = (int)$o['amount_received'] - (int)$o['amount_refunded'];
                    $pendingRefund = (int)Db::val("SELECT COALESCE(SUM(amount),0) FROM refunds WHERE order_id = :id AND status = 'pending'", ['id' => $orderId]);
                    if ($net - $pendingRefund > 0) {
                        Db::insert('refunds', [
                            'order_id' => $orderId, 'amount' => $net - $pendingRefund, 'reason' => 'Đơn hủy khi đã thu tiền: ' . $reason,
                            'status' => 'pending', 'requested_by' => Auth::id(), 'created_at' => $now, 'updated_at' => $now,
                        ]);
                    }
                    break;

                case 'shipping>returning':
                case 'delivered>returning':
                    if ($reason === null || $reason === '') {
                        throw ApiError::validation(['reason' => 'Vui lòng ghi lý do hoàn hàng.']);
                    }
                    break;

                case 'returning>returned':
                    // $extra['inspection'] = [order_item_id => ['ok' => n, 'reject' => m]]
                    $insp = $extra['inspection'] ?? [];
                    foreach ($items as $it) {
                        $ok = max(0, (int)($insp[$it['id']]['ok'] ?? 0));
                        $rej = max(0, (int)($insp[$it['id']]['reject'] ?? 0));
                        if ($ok + $rej > (int)$it['quantity']) {
                            throw ApiError::validation(['inspection' => "Số kiểm của {$it['sku_code']} vượt số lượng đã giao."]);
                        }
                        InventoryService::returnInspected((int)$it['sku_id'], $ok, $rej, $orderId, $tk, $reason);
                        Db::update('order_items', ['qty_returned_ok' => $ok, 'qty_returned_reject' => $rej], 'id = :id', ['id' => $it['id']]);
                    }
                    // Voucher đã dùng được giữ trong lịch sử (không hoàn lượt).
                    break;
            }

            $n = Db::update('orders', $update, 'id = :id AND status = :from', ['id' => $orderId, 'from' => $from]);
            if ($n !== 1) {
                throw new ApiError('CONCURRENT_UPDATE', 'Đơn vừa được người khác cập nhật, vui lòng tải lại.', 409);
            }
            Db::insert('order_status_history', [
                'order_id' => $orderId, 'from_status' => $from, 'to_status' => $to,
                'actor_type' => $actor === 'system' ? 'system' : 'user', 'user_id' => $actor === 'system' ? null : Auth::id(),
                'reason' => $reason ?: null, 'created_at' => $now,
            ]);
            Audit::log('order.status', 'order', (string)$orderId, ['status' => $from], ['status' => $to] + array_intersect_key($update, array_flip(['carrier_name', 'tracking_code'])), $reason, $actor === 'system' ? 'system' : 'user');
            PaymentService::recalc($orderId);
            SyncService::emitOrder($orderId, 'order.status_changed');
            return ['from' => $from, 'to' => $to];
        });
    }

    private static function voucherUsage(int $orderId, string $from, string $to): void
    {
        $u = Db::one('SELECT * FROM voucher_usages WHERE order_id = :o FOR UPDATE', ['o' => $orderId]);
        if (!$u || $u['status'] !== $from) {
            return;
        }
        $sql = $to === 'used'
            ? 'UPDATE vouchers SET reserved_count = reserved_count - 1, used_count = used_count + 1 WHERE id = :v AND reserved_count > 0'
            : 'UPDATE vouchers SET reserved_count = reserved_count - 1 WHERE id = :v AND reserved_count > 0';
        Db::exec($sql, ['v' => $u['voucher_id']]);
        Db::update('voucher_usages', ['status' => $to, 'updated_at' => Clock::nowDb()], 'id = :id', ['id' => $u['id']]);
    }

    public static function updateShipping(int $orderId, array $data): void
    {
        Auth::require('orders.process');
        Db::tx(function () use ($orderId, $data) {
            $o = Db::one('SELECT * FROM orders WHERE id = :id FOR UPDATE', ['id' => $orderId]);
            if (!$o) throw ApiError::notFound();
            $upd = [
                'carrier_name'  => mb_substr(trim((string)($data['carrier_name'] ?? '')), 0, 80) ?: null,
                'tracking_code' => mb_substr(trim((string)($data['tracking_code'] ?? '')), 0, 80) ?: null,
                'updated_at'    => Clock::nowDb(),
            ];
            Db::update('orders', $upd, 'id = :id', ['id' => $orderId]);
            Audit::log('order.tracking', 'order', (string)$orderId, array_intersect_key($o, $upd), $upd);
        });
    }

    // ================================================================== HẾT HẠN

    /**
     * Tác vụ hết hạn: đọc lại trạng thái trong giao dịch trước khi hủy;
     * đơn có khoản thu hoặc sai lệch → chuyển nhân viên xử lý.
     */
    public static function expireDue(int $limit = 200): array
    {
        $ids = Db::all("SELECT id FROM orders WHERE status = 'pending' AND needs_review = 0 AND expires_at <= :n ORDER BY expires_at LIMIT :l", ['n' => Clock::nowDb(), 'l' => $limit]);
        $res = ['cancelled' => 0, 'review' => 0, 'skipped' => 0, 'failed' => 0];
        foreach ($ids as $r) {
            $id = (int)$r['id'];
            try {
                $action = Db::tx(function () use ($id) {
                    $o = Db::one('SELECT * FROM orders WHERE id = :id FOR UPDATE', ['id' => $id]);
                    if (!$o || $o['status'] !== 'pending' || $o['expires_at'] > Clock::nowDb()) {
                        return 'skipped';
                    }
                    $open = (int)Db::val("SELECT COUNT(*) FROM payment_discrepancies WHERE order_id = :id AND status = 'open'", ['id' => $id]);
                    if ((int)$o['amount_received'] > 0 || $open > 0) {
                        Db::update('orders', ['needs_review' => 1, 'review_reason' => 'Hết hạn chờ xác nhận nhưng đã có khoản thu hoặc sai lệch', 'updated_at' => Clock::nowDb()], 'id = :id', ['id' => $id]);
                        Audit::log('order.needs_review', 'order', (string)$id, null, null, 'Tác vụ hết hạn chuyển cho nhân viên', 'system');
                        SyncService::emitOrder($id, 'order.flagged');
                        return 'review';
                    }
                    self::transition($id, 'cancelled', 'Hết hạn chờ xác nhận (' . strtoupper($o['payment_method']) . ')', [], 'system');
                    return 'cancelled';
                });
                $res[$action]++;
            } catch (\Throwable $e) {
                $res['failed']++;
                Audit::error('expire_job', 'EXPIRE_FAILED', "order $id: " . $e->getMessage());
            }
        }
        return $res;
    }
}

/** @internal Tín hiệu thua tranh chấp trong giao dịch tạo đơn. */
final class RaceLost extends \RuntimeException
{
}
