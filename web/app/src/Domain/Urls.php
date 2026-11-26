<?php
declare(strict_types=1);

namespace App\Domain;

use App\Core\Db;
use App\Core\Text;

/**
 * Địa chỉ công khai một cấp, đuôi .html: /{đường-dẫn}.html
 *
 * Danh mục, sản phẩm, bài blog và trang chính sách dùng CHUNG một không gian đường dẫn,
 * nên đường dẫn phải duy nhất giữa các loại và không trùng tên trang cố định.
 * Địa chỉ cũ (/danh-muc/x, /san-pham/x, /blog/x, /chinh-sach/x, /gio-hang…) được chuyển hướng 301.
 */
final class Urls
{
    /** Trang cố định → đường dẫn (không đuôi). Đổi ở đây là đổi toàn site. */
    public const FIXED = [
        'cart' => 'gio-hang', 'checkout' => 'dat-hang', 'search' => 'tim-kiem', 'flash' => 'flash-sale',
        'blog' => 'blog', 'faq' => 'hoi-dap', 'account' => 'tai-khoan', 'login' => 'dang-nhap',
        'deletion' => 'trang-thai-xoa-du-lieu',
    ];
    /** Tiền tố dành riêng: /don-hang-{mã}.html */
    public const ORDER_PREFIX = 'don-hang-';
    /** Tên dành riêng khác (tệp/đường dẫn hệ thống) */
    private const RESERVED_EXTRA = ['index', 'sitemap', 'robots', 'admin', 'api', 'auth', 'assets', 'uploads'];

    /** Thứ tự ưu tiên khi (dữ liệu cũ) trùng đường dẫn */
    public const TYPES = ['category', 'product', 'blog', 'page'];

    /** Địa chỉ cũ dạng hai cấp của từng loại — dùng để chuyển hướng 301 */
    public const LEGACY_PREFIX = ['category' => '/danh-muc/', 'product' => '/san-pham/', 'blog' => '/blog/', 'page' => '/chinh-sach/'];

    public static function to(string $slug): string
    {
        return '/' . $slug . '.html';
    }

    public static function fixed(string $key, array $query = []): string
    {
        return self::to(self::FIXED[$key]) . ($query ? '?' . http_build_query($query) : '');
    }

    public static function order(string $code, ?string $token = null): string
    {
        return self::to(self::ORDER_PREFIX . $code) . ($token !== null ? '?t=' . rawurlencode($token) : '');
    }

    public static function isReserved(string $slug): bool
    {
        return in_array($slug, self::FIXED, true) || in_array($slug, self::RESERVED_EXTRA, true) || str_starts_with($slug, self::ORDER_PREFIX);
    }

    /**
     * Đường dẫn đã có chủ chưa (bất kỳ loại nào). $type/$id: bỏ qua chính bản ghi đang sửa.
     * Hỏi đáp (faq) không có trang riêng nên không tính.
     */
    public static function isTaken(string $slug, ?string $type = null, ?int $id = null): bool
    {
        if (self::isReserved($slug)) return true;
        $ex = fn(string $t) => $t === $type ? (int)$id : 0;
        return (bool)Db::val(
            "SELECT 1 FROM categories WHERE slug = :s1 AND id <> :e1
             UNION ALL SELECT 1 FROM products WHERE slug = :s2 AND id <> :e2
             UNION ALL SELECT 1 FROM contents WHERE slug = :s3 AND kind IN ('blog','page') AND id <> :e3
             LIMIT 1",
            ['s1' => $slug, 'e1' => $ex('category'), 's2' => $slug, 'e2' => $ex('product'), 's3' => $slug,
             'e3' => in_array($type, ['blog', 'page'], true) ? (int)$id : 0]
        );
    }

    /** Đường dẫn duy nhất toàn site từ chuỗi gốc (thêm -2, -3… khi trùng). */
    public static function unique(string $base, ?string $type = null, ?int $id = null): string
    {
        $base = Text::slug($base) ?: 'trang';
        $base = substr($base, 0, 200);
        $slug = $base;
        for ($i = 2; self::isTaken($slug, $type, $id); $i++) $slug = $base . '-' . $i;
        return $slug;
    }

    /**
     * Tìm chủ của /{slug}.html theo thứ tự ưu tiên. Trả về ['type' => …, 'slug' => …] hoặc null.
     * Sản phẩm ngừng bán vẫn trả về để trang sản phẩm hiện thông báo ngừng bán (giữ hành vi cũ).
     */
    public static function resolve(string $slug): ?array
    {
        if (Db::val('SELECT 1 FROM categories WHERE slug = :s AND is_active = 1', ['s' => $slug])) return ['type' => 'category', 'slug' => $slug];
        if (Db::val("SELECT 1 FROM products WHERE slug = :s AND status IN ('active','discontinued')", ['s' => $slug])) return ['type' => 'product', 'slug' => $slug];
        $k = Db::val("SELECT kind FROM contents WHERE slug = :s AND kind IN ('blog','page') AND status = 'published' ORDER BY kind = 'blog' DESC LIMIT 1", ['s' => $slug]);
        return $k ? ['type' => $k, 'slug' => $slug] : null;
    }

    /**
     * Địa chỉ mới cho một địa chỉ cũ hai cấp (/san-pham/x…) hoặc null.
     * Đường dẫn đã bị đổi khi chuyển sang một cấp (do trùng) được tra trong url_aliases.
     */
    public static function legacyTarget(string $type, string $slug): ?string
    {
        $alias = Db::one('SELECT entity_type, entity_id FROM url_aliases WHERE old_path = :p', ['p' => self::LEGACY_PREFIX[$type] . $slug]);
        if ($alias) {
            $table = ['category' => 'categories', 'product' => 'products'][$alias['entity_type']] ?? 'contents';
            $cur = Db::val("SELECT slug FROM $table WHERE id = :id", ['id' => (int)$alias['entity_id']]);
            return $cur ? self::to($cur) : null;
        }
        $exists = match ($type) {
            'category' => Db::val('SELECT 1 FROM categories WHERE slug = :s', ['s' => $slug]),
            'product' => Db::val('SELECT 1 FROM products WHERE slug = :s', ['s' => $slug]),
            default => Db::val('SELECT 1 FROM contents WHERE kind = :k AND slug = :s', ['k' => $type, 's' => $slug]),
        };
        return $exists ? self::to($slug) : null;
    }
}
