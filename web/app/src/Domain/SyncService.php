<?php
declare(strict_types=1);

namespace App\Domain;

use App\Core\ApiError;
use App\Core\Clock;
use App\Core\Db;
use App\Core\Settings;
use App\Core\Ulid;

/**
 * Đồng bộ với dịch vụ Python (đặc tả §5.3).
 *
 * - Sự kiện được ghi CÙNG giao dịch với thay đổi đơn.
 * - seq lấy từ sync_counter bằng SELECT ... FOR UPDATE; khóa giữ đến khi commit,
 *   nên giao dịch cấp seq sau luôn commit sau → con trỏ phản ánh đúng thứ tự commit,
 *   không bỏ sót sự kiện của giao dịch chậm (lỗi kinh điển khi dùng AUTO_INCREMENT).
 * - Payload là TRẠNG THÁI tối thiểu của đơn (không tên/SĐT/địa chỉ), kèm version = seq,
 *   nên áp dụng lặp lại là an toàn (idempotent).
 */
final class SyncService
{
    public static function nextSeq(): int
    {
        if (!Db::inTx()) {
            throw new \LogicException('Sự kiện đồng bộ phải ghi trong giao dịch.');
        }
        Db::one('SELECT last_seq FROM sync_counter WHERE id = 1 FOR UPDATE');
        Db::exec('UPDATE sync_counter SET last_seq = last_seq + 1 WHERE id = 1');
        return (int)Db::val('SELECT last_seq FROM sync_counter WHERE id = 1');
    }

    public static function emit(string $entityType, int $entityId, string $eventType, array $payload): int
    {
        $seq = self::nextSeq();
        $payload['version'] = $seq;
        Db::insert('sync_events', [
            'seq'         => $seq,
            'event_id'    => Ulid::generate(),
            'entity_type' => $entityType,
            'entity_id'   => $entityId,
            'event_type'  => $eventType,
            'payload'     => json_enc($payload),
            'created_at'  => Clock::nowDb(),
        ]);
        return $seq;
    }

    /** Gọi ở CUỐI mỗi giao dịch thay đổi đơn. */
    public static function emitOrder(int $orderId, string $eventType): int
    {
        $seq = self::nextSeq();
        $payload = self::orderState($orderId);
        $payload['version'] = $seq;
        Db::insert('sync_events', [
            'seq'         => $seq,
            'event_id'    => Ulid::generate(),
            'entity_type' => 'order',
            'entity_id'   => $orderId,
            'event_type'  => $eventType,
            'payload'     => json_enc($payload),
            'created_at'  => Clock::nowDb(),
        ]);
        Db::exec('UPDATE orders SET last_event_seq = :s WHERE id = :id', ['s' => $seq, 'id' => $orderId]);
        return $seq;
    }

    /** Trạng thái đơn tối thiểu cho Python — giới hạn theo mục đích (§6). */
    public static function orderState(int $orderId, ?array $order = null): array
    {
        $o = $order ?? Db::one('SELECT o.*, c.customer_key, c.marketing_consent FROM orders o JOIN customers c ON c.id = o.customer_id WHERE o.id = :id', ['id' => $orderId]);
        $items = Db::all('SELECT sku_id, product_id, category_id, quantity AS qty, unit_price FROM order_items WHERE order_id = :id ORDER BY id', ['id' => $orderId]);
        return [
            'order_id'          => (int)$o['id'],
            'code'              => $o['code'],
            'status'            => $o['status'],
            'payment_method'    => $o['payment_method'],
            'payment_status'    => $o['payment_status'],
            'customer_key'      => $o['customer_key'],
            'marketing_consent' => (bool)$o['marketing_consent'],
            'zone_id'           => (int)$o['zone_id'],
            'goods_subtotal'    => (int)$o['goods_subtotal'],
            'voucher_code'      => $o['voucher_code'],
            'total'             => (int)$o['total'],
            'created_at'        => $o['created_at'],
            'delivered_at'      => $o['delivered_at'],
            'items'             => array_map(fn($i) => array_map('intval', $i), $items),
            'version'           => (int)$o['last_event_seq'],
        ];
    }

    public static function emitProduct(int $productId): void
    {
        $p = Db::one('SELECT id, category_id, status, info_version FROM products WHERE id = :id', ['id' => $productId]);
        if ($p) {
            self::emit('product', $productId, 'product.updated', [
                'product_id' => (int)$p['id'], 'category_id' => (int)$p['category_id'],
                'status' => $p['status'], 'info_version' => (int)$p['info_version'],
            ]);
        }
    }

    // ------------------------------------------------------------------ đọc

    public static function events(int $after, int $limit): array
    {
        $limit = max(1, min($limit, 1000));
        $prunedThrough = Settings::int('sync_pruned_through', 0);
        if ($after < $prunedThrough) {
            throw new ApiError('CURSOR_EXPIRED', 'Con trỏ đã hết hiệu lực, hãy tải lại bản chụp dữ liệu.', 410, ['pruned_through' => $prunedThrough]);
        }
        $rows = Db::all('SELECT seq, event_id, entity_type, entity_id, event_type, payload, created_at FROM sync_events WHERE seq > :a ORDER BY seq LIMIT :l', ['a' => $after, 'l' => $limit + 1]);
        $hasMore = count($rows) > $limit;
        $rows = array_slice($rows, 0, $limit);
        $events = array_map(fn($r) => [
            'seq' => (int)$r['seq'], 'event_id' => $r['event_id'], 'entity_type' => $r['entity_type'],
            'entity_id' => (int)$r['entity_id'], 'event_type' => $r['event_type'],
            'payload' => json_dec($r['payload']), 'created_at' => $r['created_at'],
        ], $rows);
        return [
            'events'      => $events,
            'next_cursor' => $events ? end($events)['seq'] : $after,
            'has_more'    => $hasMore,
        ];
    }

    /**
     * Bản chụp phân trang. as_of_seq đọc TRƯỚC dữ liệu trong cùng snapshot nhất quán:
     * mọi thay đổi sau đó có seq > as_of_seq và sẽ được phát lại qua events.
     */
    public static function snapshot(int $afterId, int $limit): array
    {
        $limit = max(1, min($limit, 1000));
        $pdo = Db::pdo();
        $pdo->exec('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ');
        $pdo->exec('START TRANSACTION WITH CONSISTENT SNAPSHOT');
        try {
            $asOf = (int)Db::val('SELECT last_seq FROM sync_counter WHERE id = 1');
            $orders = Db::all('SELECT o.*, c.customer_key, c.marketing_consent FROM orders o JOIN customers c ON c.id = o.customer_id WHERE o.id > :a ORDER BY o.id LIMIT :l', ['a' => $afterId, 'l' => $limit]);
            $out = [];
            foreach ($orders as $o) {
                $out[] = self::orderState((int)$o['id'], $o);
            }
            $products = $afterId === 0 ? Db::all('SELECT id AS product_id, category_id, status, info_version FROM products') : [];
            $pdo->commit();
        } catch (\Throwable $e) {
            $pdo->rollBack();
            throw $e;
        }
        return [
            'as_of_seq'     => $asOf,
            'orders'        => $out,
            'products'      => array_map(fn($p) => ['product_id' => (int)$p['product_id'], 'category_id' => (int)$p['category_id'], 'status' => $p['status'], 'info_version' => (int)$p['info_version']], $products),
            'next_after_id' => $out ? end($out)['order_id'] : null,
        ];
    }

    /** Thông tin sản phẩm đã duyệt cho tác nhân nội dung (dữ liệu công khai). */
    public static function catalog(): array
    {
        $cats = Db::all('SELECT id, name, slug, repurchase_days FROM categories WHERE is_active = 1 ORDER BY sort_order');
        $products = Db::all("SELECT id, category_id, name, slug, short_desc, description, ingredients, usage_guide, storage_guide, allergens, keywords, info_version, updated_at FROM products WHERE status = 'active' ORDER BY id");
        $skus = Db::all("SELECT product_id, id, sku_code, variant_label, net_weight_g, price FROM skus WHERE status = 'active' ORDER BY product_id, sort_order");
        $byP = [];
        foreach ($skus as $s) {
            $byP[$s['product_id']][] = ['sku_id' => (int)$s['id'], 'sku_code' => $s['sku_code'], 'variant_label' => $s['variant_label'], 'net_weight_g' => $s['net_weight_g'] === null ? null : (int)$s['net_weight_g'], 'list_price' => (int)$s['price']];
        }
        foreach ($products as &$p) {
            $p['id'] = (int)$p['id'];
            $p['category_id'] = (int)$p['category_id'];
            $p['info_version'] = (int)$p['info_version'];
            $p['description'] = \App\Core\Text::excerpt((string)$p['description'], 2000);
            $p['skus'] = $byP[$p['id']] ?? [];
        }
        $faqs = Db::all("SELECT id, pub_title AS question, pub_body AS answer, pub_search_text AS search_text, published_version_id AS version_id, category_id, product_id, updated_at FROM contents WHERE kind = 'faq' AND status = 'published'");
        foreach ($faqs as &$f) {
            $f['answer'] = \App\Core\Text::excerpt((string)$f['answer'], 2000);
        }
        return ['categories' => $cats, 'products' => $products, 'published_faqs' => $faqs, 'generated_at' => Clock::nowDb()];
    }

    /** Dọn sự kiện cũ; ghi lại mốc để trả CURSOR_EXPIRED đúng. */
    public static function prune(): int
    {
        $days = Settings::int('sync_event_retention_days', 30);
        $cut = Clock::db(Clock::now()->modify("-{$days} days"));
        $maxSeq = (int)Db::val('SELECT COALESCE(MAX(seq),0) FROM sync_events WHERE created_at < :c', ['c' => $cut]);
        if ($maxSeq === 0) {
            return 0;
        }
        $n = Db::exec('DELETE FROM sync_events WHERE seq <= :s', ['s' => $maxSeq]);
        Settings::set('sync_pruned_through', (string)$maxSeq);
        return $n;
    }
}
