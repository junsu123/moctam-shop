<?php
declare(strict_types=1);

namespace App\Domain;

use App\Core\ApiError;
use App\Core\Audit;
use App\Core\Auth;
use App\Core\Clock;
use App\Core\Db;
use App\Core\Html;
use App\Core\Text;

/** Danh mục, tìm kiếm (FR-01), chi tiết sản phẩm (FR-02) và quản trị sản phẩm. */
final class CatalogService
{
    public static function categories(): array
    {
        return Db::all('SELECT c.*, (SELECT COUNT(*) FROM products p WHERE p.category_id = c.id AND p.status = \'active\') AS product_count FROM categories c WHERE c.is_active = 1 ORDER BY sort_order, id');
    }

    /**
     * Tìm theo tên, SKU, từ khóa có dấu/không dấu. Chỉ sản phẩm công khai, có phân trang.
     * @return array{items:array,total:int,page:int,pages:int}
     */
    public static function search(string $q = '', ?int $categoryId = null, int $page = 1, int $perPage = 12, string $sort = 'default'): array
    {
        $where = ["p.status = 'active'", "EXISTS (SELECT 1 FROM skus s WHERE s.product_id = p.id AND s.status = 'active')"];
        $params = [];
        foreach (array_slice(Text::tokens($q), 0, 6) as $i => $tok) {
            $where[] = "p.search_text LIKE :t$i";
            $params["t$i"] = '%' . str_replace(['%', '_'], ['\\%', '\\_'], $tok) . '%';
        }
        if ($categoryId) {
            $where[] = 'p.category_id = :cat';
            $params['cat'] = $categoryId;
        }
        $w = implode(' AND ', $where);
        $total = (int)Db::val("SELECT COUNT(*) FROM products p WHERE $w", $params);
        $pages = max(1, (int)ceil($total / $perPage));
        $page = max(1, min($page, $pages));
        $order = match ($sort) {
            'price_asc'  => 'min_price ASC',
            'price_desc' => 'min_price DESC',
            'newest'     => 'p.created_at DESC',
            default      => 'p.is_featured DESC, p.id ASC',
        };
        $rows = Db::all(
            "SELECT p.id, p.name, p.slug, p.short_desc, p.category_id,
                    (SELECT MIN(price) FROM skus s WHERE s.product_id = p.id AND s.status = 'active') AS min_price,
                    (SELECT path FROM product_images im WHERE im.product_id = p.id ORDER BY sort_order LIMIT 1) AS image,
                    (SELECT COALESCE(SUM(GREATEST(i.on_hand - i.reserved,0)),0) FROM skus s JOIN inventory i ON i.sku_id = s.id WHERE s.product_id = p.id AND s.status = 'active') AS available
               FROM products p WHERE $w ORDER BY $order LIMIT :lim OFFSET :off",
            $params + ['lim' => $perPage, 'off' => ($page - 1) * $perPage]
        );
        return ['items' => self::attachFlash($rows), 'total' => $total, 'page' => $page, 'pages' => $pages];
    }

    /** Gắn giá Flash Sale thấp nhất của mỗi sản phẩm (để hiện giá gạch ngang có căn cứ). */
    public static function attachFlash(array $rows): array
    {
        if (!$rows) return $rows;
        $pids = array_column($rows, 'id');
        $in = implode(',', array_fill(0, count($pids), '?'));
        $skus = Db::all("SELECT id, product_id, price FROM skus WHERE product_id IN ($in) AND status = 'active'", $pids);
        $flash = PricingService::activeFlashPrices(array_column($skus, 'id'));
        $best = [];
        foreach ($skus as $s) {
            if (isset($flash[$s['id']])) {
                $sale = (int)$flash[$s['id']]['sale_price'];
                if (!isset($best[$s['product_id']]) || $sale < $best[$s['product_id']]['sale']) {
                    $best[$s['product_id']] = ['sale' => $sale, 'list' => (int)$s['price'], 'ends_at' => $flash[$s['id']]['ends_at']];
                }
            }
        }
        foreach ($rows as &$r) {
            $r['flash'] = $best[$r['id']] ?? null;
        }
        return $rows;
    }

    public static function productBySlug(string $slug): ?array
    {
        $p = Db::one("SELECT p.*, c.name AS category_name, c.slug AS category_slug FROM products p JOIN categories c ON c.id = p.category_id WHERE p.slug = :s AND p.status = 'active'", ['s' => $slug]);
        if (!$p) return null;
        $p['images'] = Db::all('SELECT path, alt FROM product_images WHERE product_id = :id ORDER BY sort_order', ['id' => $p['id']]);
        $skus = Db::all("SELECT s.id, s.sku_code, s.variant_label, s.net_weight_g, s.price, GREATEST(COALESCE(i.on_hand,0) - COALESCE(i.reserved,0), 0) AS available
                           FROM skus s LEFT JOIN inventory i ON i.sku_id = s.id WHERE s.product_id = :id AND s.status = 'active' ORDER BY s.sort_order, s.id", ['id' => $p['id']]);
        $flash = PricingService::activeFlashPrices(array_column($skus, 'id'));
        foreach ($skus as &$s) {
            $f = $flash[$s['id']] ?? null;
            $s['price'] = (int)$s['price'];
            $s['available'] = (int)$s['available'];
            $s['sale_price'] = $f ? (int)$f['sale_price'] : null;
            $s['flash_ends_at'] = $f['ends_at'] ?? null;
        }
        $p['skus'] = $skus;
        // Lượt bán thực tế: chỉ tính đơn đã giao, không tính hoàn (có căn cứ — FR-02)
        $p['sold_count'] = (int)Db::val("SELECT COALESCE(SUM(oi.quantity - oi.qty_returned_ok - oi.qty_returned_reject),0) FROM order_items oi JOIN orders o ON o.id = oi.order_id WHERE oi.product_id = :id AND o.status = 'delivered'", ['id' => $p['id']]);
        $p['related'] = self::attachFlash(Db::all(
            "SELECT p2.id, p2.name, p2.slug, p2.short_desc,
                    (SELECT MIN(price) FROM skus s WHERE s.product_id = p2.id AND s.status = 'active') AS min_price,
                    (SELECT path FROM product_images im WHERE im.product_id = p2.id ORDER BY sort_order LIMIT 1) AS image,
                    (SELECT id FROM skus s WHERE s.product_id = p2.id AND s.status = 'active' ORDER BY sort_order, id LIMIT 1) AS default_sku_id,
                    1 AS available
               FROM product_relations r JOIN products p2 ON p2.id = r.related_product_id
              WHERE r.product_id = :id AND r.status = 'approved' AND p2.status = 'active'
              ORDER BY r.sort_order, r.id LIMIT 4",
            ['id' => $p['id']]
        ));
        return $p;
    }

    public static function featured(int $limit = 8): array
    {
        return self::search('', null, 1, $limit)['items'];
    }

    // ------------------------------------------------------------ QUẢN TRỊ

    public static function saveProduct(?int $id, array $in): int
    {
        Auth::require('catalog.manage');
        $name = trim((string)($in['name'] ?? ''));
        $data = [
            'category_id'   => (int)($in['category_id'] ?? 0),
            'name'          => mb_substr($name, 0, 200),
            'short_desc'    => mb_substr(trim((string)($in['short_desc'] ?? '')), 0, 500) ?: null,
            'description'   => Html::sanitize((string)($in['description'] ?? '')),
            'ingredients'   => trim((string)($in['ingredients'] ?? '')) ?: null,
            'usage_guide'   => trim((string)($in['usage_guide'] ?? '')) ?: null,
            'storage_guide' => trim((string)($in['storage_guide'] ?? '')) ?: null,
            'allergens'     => trim((string)($in['allergens'] ?? '')) ?: null,
            'keywords'      => mb_substr(trim((string)($in['keywords'] ?? '')), 0, 500) ?: null,
            'status'        => in_array($in['status'] ?? '', ['draft', 'active', 'discontinued'], true) ? $in['status'] : 'draft',
            'is_featured'   => !empty($in['is_featured']) ? 1 : 0,
            'updated_at'    => Clock::nowDb(),
        ];
        $err = [];
        if (mb_strlen($name) < 2) $err['name'] = 'Bắt buộc';
        if (!Db::val('SELECT 1 FROM categories WHERE id = :id', ['id' => $data['category_id']])) $err['category_id'] = 'Chọn danh mục';
        if ($err) throw ApiError::validation($err);

        return Db::tx(function () use ($id, $data, $in) {
            $labelFields = ['name', 'description', 'ingredients', 'usage_guide', 'storage_guide', 'allergens'];
            if ($id) {
                $before = Db::one('SELECT * FROM products WHERE id = :id FOR UPDATE', ['id' => $id]);
                if (!$before) throw ApiError::notFound();
                $changed = false;
                foreach ($labelFields as $f) {
                    if ((string)$before[$f] !== (string)$data[$f]) $changed = true;
                }
                if ($changed) $data['info_version'] = (int)$before['info_version'] + 1;
                Db::update('products', $data, 'id = :id', ['id' => $id]);
                Audit::log('product.update', 'product', (string)$id, array_intersect_key($before, $data), $data);
            } else {
                $slug = self::uniqueSlug(Text::slug($in['slug'] ?? '' ?: $data['name']));
                $id = Db::insert('products', $data + ['slug' => $slug, 'search_text' => '', 'created_at' => Clock::nowDb()]);
                Audit::log('product.create', 'product', (string)$id, null, $data);
            }
            self::refreshSearchText($id);
            SyncService::emitProduct($id);
            return $id;
        });
    }

    public static function uniqueSlug(string $slug): string
    {
        $base = $slug;
        $i = 2;
        while (Db::val('SELECT 1 FROM products WHERE slug = :s', ['s' => $slug])) {
            $slug = $base . '-' . $i++;
        }
        return $slug;
    }

    public static function refreshSearchText(int $productId): void
    {
        $p = Db::one('SELECT p.name, p.keywords, p.short_desc, c.name AS cat FROM products p JOIN categories c ON c.id = p.category_id WHERE p.id = :id', ['id' => $productId]);
        $skus = Db::all('SELECT sku_code, variant_label FROM skus WHERE product_id = :id', ['id' => $productId]);
        $text = Text::fold(implode(' ', array_merge([$p['name'], $p['keywords'], $p['short_desc'], $p['cat']], array_column($skus, 'sku_code'), array_column($skus, 'variant_label'))));
        Db::exec('UPDATE products SET search_text = :t WHERE id = :id', ['t' => $text, 'id' => $productId]);
    }

    /** Thêm/sửa quy cách (SKU). Giá thay đổi được ghi nhật ký (FR-12). */
    public static function saveSku(int $productId, ?int $skuId, array $in): int
    {
        Auth::require('catalog.manage');
        $data = [
            'sku_code'      => strtoupper(preg_replace('/[^A-Za-z0-9_-]/', '', (string)($in['sku_code'] ?? '')) ?? ''),
            'variant_label' => mb_substr(trim((string)($in['variant_label'] ?? '')), 0, 120),
            'net_weight_g'  => ($in['net_weight_g'] ?? '') === '' ? null : max(0, (int)$in['net_weight_g']),
            'price'         => (int)($in['price'] ?? 0),
            'status'        => ($in['status'] ?? 'active') === 'discontinued' ? 'discontinued' : 'active',
            'sort_order'    => (int)($in['sort_order'] ?? 0),
            'updated_at'    => Clock::nowDb(),
        ];
        $err = [];
        if (strlen($data['sku_code']) < 3) $err['sku_code'] = 'SKU tối thiểu 3 ký tự';
        if ($data['variant_label'] === '') $err['variant_label'] = 'Bắt buộc (VD: Hộp 20 túi)';
        if ($data['price'] <= 0) $err['price'] = 'Giá phải > 0';
        if ($err) throw ApiError::validation($err);

        return Db::tx(function () use ($productId, $skuId, $data) {
            try {
                if ($skuId) {
                    $before = Db::one('SELECT * FROM skus WHERE id = :id AND product_id = :p FOR UPDATE', ['id' => $skuId, 'p' => $productId]);
                    if (!$before) throw ApiError::notFound();
                    Db::update('skus', $data, 'id = :id', ['id' => $skuId]);
                    $action = (int)$before['price'] !== $data['price'] ? 'sku.price_change' : 'sku.update';
                    Audit::log($action, 'sku', (string)$skuId, array_intersect_key($before, $data), $data);
                } else {
                    $skuId = Db::insert('skus', $data + ['product_id' => $productId, 'created_at' => Clock::nowDb()]);
                    Db::insert('inventory', ['sku_id' => $skuId, 'on_hand' => 0, 'reserved' => 0, 'updated_at' => Clock::nowDb()]);
                    Audit::log('sku.create', 'sku', (string)$skuId, null, $data);
                }
            } catch (\PDOException $e) {
                if (Db::isDuplicate($e)) throw ApiError::validation(['sku_code' => 'Mã SKU đã tồn tại']);
                throw $e;
            }
            self::refreshSearchText($productId);
            return $skuId;
        });
    }

    /** Sản phẩm từng có trong đơn không bị xóa, chỉ ngừng bán. */
    public static function deleteOrDiscontinue(int $productId): string
    {
        Auth::require('catalog.manage');
        return Db::tx(function () use ($productId) {
            $used = (int)Db::val('SELECT COUNT(*) FROM order_items WHERE product_id = :id', ['id' => $productId]);
            if ($used > 0) {
                Db::exec("UPDATE products SET status = 'discontinued', updated_at = :t WHERE id = :id", ['id' => $productId, 't' => Clock::nowDb()]);
                Audit::log('product.discontinue', 'product', (string)$productId, null, ['status' => 'discontinued'], 'Sản phẩm có trong đơn: ngừng bán thay vì xóa');
                SyncService::emitProduct($productId);
                return 'discontinued';
            }
            $skuIds = array_column(Db::all('SELECT id FROM skus WHERE product_id = :id', ['id' => $productId]), 'id');
            foreach ($skuIds as $sid) {
                Db::exec('DELETE FROM inventory_movements WHERE sku_id = :s', ['s' => $sid]);
                Db::exec('DELETE FROM flash_sale_items WHERE sku_id = :s', ['s' => $sid]);
                Db::exec('DELETE FROM inventory WHERE sku_id = :s', ['s' => $sid]);
            }
            Db::exec('DELETE FROM skus WHERE product_id = :id', ['id' => $productId]);
            Db::exec('DELETE FROM products WHERE id = :id', ['id' => $productId]);
            Audit::log('product.delete', 'product', (string)$productId);
            return 'deleted';
        });
    }

    public static function addImage(int $productId, array $file, string $alt): void
    {
        Auth::require('catalog.manage');
        if (($file['error'] ?? UPLOAD_ERR_NO_FILE) !== UPLOAD_ERR_OK) throw ApiError::validation(['image' => 'Tải ảnh thất bại']);
        if ($file['size'] > 3 * 1024 * 1024) throw ApiError::validation(['image' => 'Ảnh tối đa 3MB']);
        $mime = (new \finfo(FILEINFO_MIME_TYPE))->file($file['tmp_name']);
        $ext = ['image/jpeg' => 'jpg', 'image/png' => 'png', 'image/webp' => 'webp'][$mime] ?? null;
        if (!$ext || !@getimagesize($file['tmp_name'])) throw ApiError::validation(['image' => 'Chỉ nhận JPG, PNG, WEBP']);
        $dir = rtrim((string)config('paths.uploads'), '/') . '/products';
        if (!is_dir($dir)) mkdir($dir, 0755, true);
        $name = $productId . '-' . bin2hex(random_bytes(6)) . '.' . $ext;
        if (!move_uploaded_file($file['tmp_name'], "$dir/$name")) throw ApiError::validation(['image' => 'Không lưu được ảnh']);
        $sort = (int)Db::val('SELECT COALESCE(MAX(sort_order),0)+1 FROM product_images WHERE product_id = :id', ['id' => $productId]);
        Db::insert('product_images', ['product_id' => $productId, 'path' => '/uploads/products/' . $name, 'alt' => mb_substr($alt, 0, 200) ?: null, 'sort_order' => $sort]);
        Audit::log('product.image_add', 'product', (string)$productId, null, ['path' => $name]);
    }

    public static function saveRelation(int $productId, int $relatedId): void
    {
        Auth::require('catalog.manage');
        if ($productId === $relatedId) throw ApiError::validation(['related_product_id' => 'Không thể gợi ý chính sản phẩm này']);
        Db::run("INSERT INTO product_relations (product_id, related_product_id, source, status, created_at, reviewed_by) VALUES (:p,:r,'staff','approved',:t,:u)
                 ON DUPLICATE KEY UPDATE status = 'approved', reviewed_by = VALUES(reviewed_by)", ['p' => $productId, 'r' => $relatedId, 't' => Clock::nowDb(), 'u' => Auth::id()]);
        Audit::log('crosssell.add', 'product', (string)$productId, null, ['related' => $relatedId]);
    }

    public static function reviewRelation(int $relId, bool $approve): void
    {
        Auth::require('crosssell.review');
        $before = Db::one('SELECT * FROM product_relations WHERE id = :id', ['id' => $relId]);
        if (!$before) throw ApiError::notFound();
        Db::update('product_relations', ['status' => $approve ? 'approved' : 'rejected', 'reviewed_by' => Auth::id()], 'id = :id', ['id' => $relId]);
        Audit::log($approve ? 'crosssell.approve' : 'crosssell.reject', 'product_relation', (string)$relId, ['status' => $before['status']], ['status' => $approve ? 'approved' : 'rejected']);
    }
}
