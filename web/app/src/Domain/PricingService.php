<?php
declare(strict_types=1);

namespace App\Domain;

use App\Core\ApiError;
use App\Core\Clock;
use App\Core\Db;
use App\Core\Settings;

/**
 * Báo giá do MÁY CHỦ quyết định (FR-03, §4.1):
 *   Tổng = tiền hàng sau Flash Sale − giảm giá voucher + phí giao.
 * Một voucher/đơn; đơn tối thiểu tính trên tiền hàng ĐỦ ĐIỀU KIỆN sau Flash Sale, trước phí giao;
 * giảm tối đa bằng tiền hàng đủ điều kiện.
 */
final class PricingService
{
    public const MAX_LINES = 30;
    public const MAX_QTY = 99;

    /**
     * @param array<int,array{sku_id:int,qty:int}> $items
     */
    public static function quote(array $items, ?string $voucherCode, ?string $province): array
    {
        $items = self::normalizeItems($items);
        $now = Clock::nowDb();
        $lines = [];
        $issues = [];

        if ($items) {
            $ids = array_keys($items);
            $in = implode(',', array_fill(0, count($ids), '?'));
            $rows = Db::all(
                "SELECT s.id AS sku_id, s.sku_code, s.variant_label, s.price, s.status AS sku_status, s.net_weight_g,
                        p.id AS product_id, p.name AS product_name, p.slug, p.category_id, p.status AS product_status,
                        i.on_hand, i.reserved,
                        (SELECT path FROM product_images im WHERE im.product_id = p.id ORDER BY sort_order LIMIT 1) AS image
                   FROM skus s JOIN products p ON p.id = s.product_id LEFT JOIN inventory i ON i.sku_id = s.id
                  WHERE s.id IN ($in)",
                $ids
            );
            $bySku = [];
            foreach ($rows as $r) {
                $bySku[(int)$r['sku_id']] = $r;
            }
            $flash = self::activeFlashPrices($ids, $now);

            foreach ($items as $skuId => $qty) {
                $r = $bySku[$skuId] ?? null;
                if (!$r || $r['sku_status'] !== 'active' || $r['product_status'] !== 'active') {
                    $issues[] = ['sku_id' => $skuId, 'code' => 'UNAVAILABLE', 'message' => 'Sản phẩm đã ngừng bán', 'available' => 0];
                    continue;
                }
                $available = max(0, (int)$r['on_hand'] - (int)$r['reserved']);
                $fs = $flash[$skuId] ?? null;
                $unit = $fs ? min((int)$fs['sale_price'], (int)$r['price']) : (int)$r['price'];
                $line = [
                    'sku_id'           => $skuId,
                    'sku_code'         => $r['sku_code'],
                    'product_id'       => (int)$r['product_id'],
                    'product_name'     => $r['product_name'],
                    'slug'             => $r['slug'],
                    'category_id'      => (int)$r['category_id'],
                    'variant_label'    => $r['variant_label'],
                    'image'            => $r['image'],
                    'list_price'       => (int)$r['price'],
                    'unit_price'       => $unit,
                    'flash_sale_id'    => $fs ? (int)$fs['flash_sale_id'] : null,
                    'flash_ends_at'    => $fs['ends_at'] ?? null,
                    'voucher_eligible' => $fs ? (bool)$fs['allow_voucher'] : true,
                    'qty'              => $qty,
                    'line_total'       => $unit * $qty,
                    'available'        => $available,
                ];
                if ($available < $qty) {
                    $issues[] = ['sku_id' => $skuId, 'code' => $available === 0 ? 'OUT_OF_STOCK' : 'INSUFFICIENT_STOCK',
                        'message' => $available === 0 ? 'Hết hàng' : "Chỉ còn $available sản phẩm", 'available' => $available];
                }
                $lines[] = $line;
            }
        }

        $goods = array_sum(array_column($lines, 'line_total'));
        $voucher = self::evaluateVoucher($voucherCode, $lines, $now);
        $discount = $voucher['discount'] ?? 0;
        $shipping = ShippingService::quote($province, $goods - $discount);
        $total = $goods - $discount + $shipping['fee'];

        $ttl = Settings::int('quote_ttl_minutes', 15);
        $expiresAt = Clock::db(Clock::now()->modify("+{$ttl} minutes"));
        $quote = [
            'lines'          => $lines,
            'issues'         => $issues,
            'goods_subtotal' => $goods,
            'voucher'        => $voucher,
            'discount'       => $discount,
            'shipping'       => $shipping,
            'total'          => $total,
            'expires_at'     => $expiresAt,
            'currency'       => 'VND',
        ];
        $quote['fingerprint'] = self::fingerprint($quote);
        $quote['quote_token'] = self::signToken($quote['fingerprint'], $expiresAt);
        return $quote;
    }

    /** Chuẩn hóa: gộp SKU trùng, giới hạn số dòng/số lượng. @return array<int,int> sku_id => qty */
    public static function normalizeItems(array $items): array
    {
        $out = [];
        foreach ($items as $it) {
            $sku = (int)($it['sku_id'] ?? 0);
            $qty = (int)($it['qty'] ?? 0);
            if ($sku <= 0 || $qty <= 0) {
                continue;
            }
            $out[$sku] = min(self::MAX_QTY, ($out[$sku] ?? 0) + $qty);
        }
        if (count($out) > self::MAX_LINES) {
            throw ApiError::validation(['items' => 'Giỏ hàng tối đa ' . self::MAX_LINES . ' dòng sản phẩm.']);
        }
        ksort($out);
        return $out;
    }

    /** @return array<int,array> sku_id => flash item đang hiệu lực */
    public static function activeFlashPrices(array $skuIds, ?string $now = null): array
    {
        if (!$skuIds) {
            return [];
        }
        $now ??= Clock::nowDb();
        $in = implode(',', array_fill(0, count($skuIds), '?'));
        $rows = Db::all(
            "SELECT fi.sku_id, fi.sale_price, f.id AS flash_sale_id, f.ends_at, f.starts_at, f.allow_voucher, f.name
               FROM flash_sale_items fi JOIN flash_sales f ON f.id = fi.flash_sale_id
              WHERE fi.sku_id IN ($in) AND f.is_active = 1 AND f.starts_at <= ? AND f.ends_at > ?
              ORDER BY fi.sale_price ASC",
            array_merge(array_values($skuIds), [$now, $now])
        );
        $out = [];
        foreach ($rows as $r) {
            $out[(int)$r['sku_id']] ??= $r; // tối đa một chương trình/SKU; nếu dữ liệu lỗi, lấy giá thấp nhất
        }
        return $out;
    }

    public static function evaluateVoucher(?string $code, array $lines, string $now): ?array
    {
        $code = strtoupper(trim((string)$code));
        if ($code === '') {
            return null;
        }
        $v = Db::one('SELECT * FROM vouchers WHERE code = :c', ['c' => $code]);
        $fail = fn(string $err, string $msg) => ['code' => $code, 'valid' => false, 'discount' => 0, 'error_code' => $err, 'message' => $msg, 'voucher_id' => $v['id'] ?? null];
        if (!$v || !$v['is_active']) {
            return $fail('VOUCHER_INVALID', 'Mã giảm giá không tồn tại hoặc đã ngừng.');
        }
        if ($now < $v['starts_at'] || $now >= $v['ends_at']) {
            return $fail('VOUCHER_EXPIRED', 'Mã giảm giá chưa bắt đầu hoặc đã hết hạn.');
        }
        if ($v['usage_limit'] !== null && (int)$v['reserved_count'] + (int)$v['used_count'] >= (int)$v['usage_limit']) {
            return $fail('VOUCHER_EXHAUSTED', 'Mã giảm giá đã hết lượt sử dụng.');
        }
        $scopeIds = array_map('intval', json_dec($v['scope_ids']));
        $eligible = 0;
        foreach ($lines as $l) {
            if (!$l['voucher_eligible']) {
                continue;
            }
            $inScope = match ($v['scope_type']) {
                'category' => in_array($l['category_id'], $scopeIds, true),
                'product'  => in_array($l['product_id'], $scopeIds, true),
                default    => true,
            };
            if ($inScope) {
                $eligible += $l['line_total'];
            }
        }
        if ($eligible <= 0) {
            return $fail('VOUCHER_NOT_APPLICABLE', 'Mã không áp dụng cho sản phẩm trong giỏ (hoặc sản phẩm đang Flash Sale).');
        }
        if ($eligible < (int)$v['min_subtotal']) {
            return $fail('VOUCHER_MIN_NOT_MET', 'Cần mua thêm ' . money((int)$v['min_subtotal'] - $eligible) . ' sản phẩm đủ điều kiện để dùng mã.');
        }
        return [
            'code'             => $code,
            'valid'            => true,
            'voucher_id'       => (int)$v['id'],
            'discount'         => min((int)$v['amount'], $eligible),
            'eligible_subtotal'=> $eligible,
            'error_code'       => null,
            'message'          => 'Đã áp dụng mã ' . $code,
        ];
    }

    public static function fingerprint(array $q): string
    {
        $parts = [
            array_map(fn($l) => [$l['sku_id'], $l['unit_price'], $l['qty']], $q['lines']),
            $q['goods_subtotal'], $q['discount'], $q['shipping']['fee'], $q['shipping']['rate_id'], $q['total'],
            $q['voucher']['code'] ?? null,
        ];
        return hash('sha256', json_enc($parts));
    }

    public static function signToken(string $fingerprint, string $expiresAt): string
    {
        $payload = $fingerprint . '|' . strtotime($expiresAt . ' UTC');
        return base64_encode($payload) . '.' . hash_hmac('sha256', $payload, (string)config('app_key'));
    }

    /** @return array{fingerprint:string, expires:int}|null */
    public static function verifyToken(?string $token): ?array
    {
        if (!$token || !str_contains($token, '.')) {
            return null;
        }
        [$b64, $sig] = explode('.', $token, 2);
        $payload = base64_decode($b64, true);
        if ($payload === false || !hash_equals(hash_hmac('sha256', $payload, (string)config('app_key')), $sig)) {
            return null;
        }
        [$fp, $exp] = explode('|', $payload) + [null, null];
        return $fp ? ['fingerprint' => $fp, 'expires' => (int)$exp] : null;
    }

    /** Bản báo giá trả cho khách (ẩn trường nội bộ). */
    public static function present(array $q): array
    {
        return $q;
    }
}
