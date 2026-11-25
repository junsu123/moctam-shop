<?php
declare(strict_types=1);

namespace App\Domain;

use App\Core\ApiError;
use App\Core\Audit;
use App\Core\Auth;
use App\Core\Clock;
use App\Core\Db;

/** Voucher và Flash Sale (FR-07). */
final class PromotionService
{
    public static function saveVoucher(?int $id, array $in): int
    {
        Auth::require('promo.manage');
        $code = strtoupper(preg_replace('/[^A-Za-z0-9_-]/', '', (string)($in['code'] ?? '')) ?? '');
        $data = [
            'code'         => $code,
            'description'  => mb_substr(trim((string)($in['description'] ?? '')), 0, 200) ?: null,
            'amount'       => (int)($in['amount'] ?? 0),
            'min_subtotal' => max(0, (int)($in['min_subtotal'] ?? 0)),
            'scope_type'   => in_array($in['scope_type'] ?? '', ['all', 'category', 'product'], true) ? $in['scope_type'] : 'all',
            'scope_ids'    => json_enc(array_values(array_filter(array_map('intval', (array)($in['scope_ids'] ?? []))))),
            'starts_at'    => Clock::fromLocalInput((string)($in['starts_at'] ?? '')),
            'ends_at'      => Clock::fromLocalInput((string)($in['ends_at'] ?? '')),
            'usage_limit'  => ($in['usage_limit'] ?? '') === '' ? null : max(0, (int)$in['usage_limit']),
            'is_active'    => !empty($in['is_active']) ? 1 : 0,
            'updated_at'   => Clock::nowDb(),
        ];
        $err = [];
        if (strlen($code) < 3) $err['code'] = 'Mã tối thiểu 3 ký tự (chữ, số, - _)';
        if ($data['amount'] <= 0) $err['amount'] = 'Số tiền giảm phải > 0';
        if (!$data['starts_at']) $err['starts_at'] = 'Bắt buộc';
        if (!$data['ends_at'] || ($data['starts_at'] && $data['ends_at'] <= $data['starts_at'])) $err['ends_at'] = 'Phải sau thời điểm bắt đầu';
        if ($data['scope_type'] !== 'all' && json_dec($data['scope_ids']) === []) $err['scope_ids'] = 'Chọn ít nhất một mục áp dụng';
        if ($err) throw ApiError::validation($err);

        return Db::tx(function () use ($id, $data) {
            if ($id) {
                $before = Db::one('SELECT * FROM vouchers WHERE id = :id FOR UPDATE', ['id' => $id]);
                if (!$before) throw ApiError::notFound();
                if ($data['usage_limit'] !== null && $data['usage_limit'] < (int)$before['used_count'] + (int)$before['reserved_count']) {
                    throw ApiError::validation(['usage_limit' => 'Giới hạn không được nhỏ hơn số lượt đã dùng/đang giữ (' . ((int)$before['used_count'] + (int)$before['reserved_count']) . ')']);
                }
                Db::update('vouchers', $data, 'id = :id', ['id' => $id]);
                Audit::log('voucher.update', 'voucher', (string)$id, $before, $data);
                return $id;
            }
            try {
                $id = Db::insert('vouchers', $data + ['created_at' => Clock::nowDb()]);
            } catch (\PDOException $e) {
                if (Db::isDuplicate($e)) throw ApiError::validation(['code' => 'Mã đã tồn tại']);
                throw $e;
            }
            Audit::log('voucher.create', 'voucher', (string)$id, null, $data);
            return $id;
        });
    }

    /**
     * Lưu Flash Sale. Mỗi SKU tối đa MỘT chương trình hiệu lực tại một thời điểm:
     * kiểm tra chồng lấn thời gian với các chương trình đang bật khác.
     * @param array<int,int> $items sku_id => sale_price
     */
    public static function saveFlashSale(?int $id, array $in, array $items): int
    {
        Auth::require('promo.manage');
        $data = [
            'name'          => mb_substr(trim((string)($in['name'] ?? '')), 0, 150),
            'starts_at'     => Clock::fromLocalInput((string)($in['starts_at'] ?? '')),
            'ends_at'       => Clock::fromLocalInput((string)($in['ends_at'] ?? '')),
            'allow_voucher' => !empty($in['allow_voucher']) ? 1 : 0,
            'is_active'     => !empty($in['is_active']) ? 1 : 0,
            'updated_at'    => Clock::nowDb(),
        ];
        $err = [];
        if ($data['name'] === '') $err['name'] = 'Bắt buộc';
        if (!$data['starts_at']) $err['starts_at'] = 'Bắt buộc';
        if (!$data['ends_at'] || ($data['starts_at'] && $data['ends_at'] <= $data['starts_at'])) $err['ends_at'] = 'Phải sau thời điểm bắt đầu';
        $items = array_filter(array_map('intval', $items), fn($p) => $p > 0);
        if (!$items) $err['items'] = 'Thêm ít nhất một SKU với giá Flash Sale';
        if ($err) throw ApiError::validation($err);

        return Db::tx(function () use ($id, $data, $items) {
            Db::all('SELECT id FROM flash_sales FOR UPDATE'); // tuần tự hóa việc lưu để kiểm tra chồng lấn chính xác
            $ids = array_keys($items);
            $in = implode(',', array_fill(0, count($ids), '?'));
            $skus = Db::all("SELECT id, sku_code, price FROM skus WHERE id IN ($in)", $ids);
            $byId = array_column($skus, null, 'id');
            foreach ($items as $skuId => $price) {
                if (!isset($byId[$skuId])) throw ApiError::validation(['items' => "SKU #$skuId không tồn tại"]);
                if ($price >= (int)$byId[$skuId]['price']) {
                    throw ApiError::validation(['items' => "Giá Flash Sale của {$byId[$skuId]['sku_code']} phải thấp hơn giá niêm yết " . money($byId[$skuId]['price'])]);
                }
            }
            if ($data['is_active']) {
                $conflicts = Db::all(
                    "SELECT s.sku_code, f.name FROM flash_sale_items fi JOIN flash_sales f ON f.id = fi.flash_sale_id JOIN skus s ON s.id = fi.sku_id
                      WHERE fi.sku_id IN ($in) AND f.is_active = 1 AND f.id <> ? AND f.starts_at < ? AND f.ends_at > ?",
                    array_merge($ids, [$id ?? 0, $data['ends_at'], $data['starts_at']])
                );
                if ($conflicts) {
                    $c = $conflicts[0];
                    throw ApiError::validation(['items' => "SKU {$c['sku_code']} đã thuộc Flash Sale \"{$c['name']}\" trong khoảng thời gian chồng lấn."]);
                }
            }
            $before = null;
            if ($id) {
                $before = Db::one('SELECT * FROM flash_sales WHERE id = :id', ['id' => $id]);
                if (!$before) throw ApiError::notFound();
                $before['items'] = Db::all('SELECT sku_id, sale_price FROM flash_sale_items WHERE flash_sale_id = :id', ['id' => $id]);
                Db::update('flash_sales', $data, 'id = :id', ['id' => $id]);
                Db::exec('DELETE FROM flash_sale_items WHERE flash_sale_id = :id', ['id' => $id]);
            } else {
                $id = Db::insert('flash_sales', $data + ['created_at' => Clock::nowDb()]);
            }
            foreach ($items as $skuId => $price) {
                Db::insert('flash_sale_items', ['flash_sale_id' => $id, 'sku_id' => $skuId, 'sale_price' => $price]);
            }
            Audit::log($before ? 'flash_sale.update' : 'flash_sale.create', 'flash_sale', (string)$id, $before, $data + ['items' => $items]);
            return $id;
        });
    }

    /** Flash Sale đang chạy cho trang chủ. */
    public static function activeFlashSale(): ?array
    {
        $now = Clock::nowDb();
        $fs = Db::one('SELECT * FROM flash_sales WHERE is_active = 1 AND starts_at <= :n AND ends_at > :n2 ORDER BY ends_at LIMIT 1', ['n' => $now, 'n2' => $now]);
        if (!$fs) return null;
        $fs['items'] = Db::all(
            "SELECT fi.sale_price, s.id AS sku_id, s.price, s.variant_label, p.name, p.slug,
                    (SELECT path FROM product_images im WHERE im.product_id = p.id ORDER BY sort_order LIMIT 1) AS image,
                    GREATEST(i.on_hand - i.reserved, 0) AS available
               FROM flash_sale_items fi JOIN skus s ON s.id = fi.sku_id JOIN products p ON p.id = s.product_id
               LEFT JOIN inventory i ON i.sku_id = s.id
              WHERE fi.flash_sale_id = :id AND s.status = 'active' AND p.status = 'active'",
            ['id' => $fs['id']]
        );
        return $fs;
    }
}
