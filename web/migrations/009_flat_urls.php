<?php
declare(strict_types=1);

/*
 * 009 — Địa chỉ một cấp, đuôi .html (/{slug}.html).
 *
 * Danh mục, sản phẩm, bài blog và trang chính sách từ nay dùng chung một không gian đường dẫn.
 * 1. Bảng url_aliases: địa chỉ cũ của các mục phải đổi đường dẫn → vẫn chuyển hướng 301 đúng chỗ.
 * 2. Mục nào trùng đường dẫn với mục ưu tiên hơn (danh mục > sản phẩm > blog > trang) hoặc trùng tên
 *    trang cố định (gio-hang, dat-hang, blog…) được đổi sang đường dẫn mới có hậu tố, ghi nhật ký.
 * 3. Trang pháp lý: cập nhật liên kết sang địa chỉ mới (chưa bị xưởng sửa → xuất bản; đã sửa → chờ duyệt).
 */

use App\Core\Audit;
use App\Core\Clock;
use App\Core\Db;
use App\Domain\Urls;

Db::exec("CREATE TABLE IF NOT EXISTS url_aliases (
  old_path    VARCHAR(255) NOT NULL PRIMARY KEY COMMENT 'Địa chỉ cũ hai cấp, VD /san-pham/tra-gung',
  entity_type ENUM('category','product','blog','page') NOT NULL,
  entity_id   INT UNSIGNED NOT NULL,
  created_at  DATETIME NOT NULL,
  KEY idx_alias_entity (entity_type, entity_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci");

$suffix = ['category' => 'danh-muc', 'product' => 'san-pham', 'blog' => 'bai-viet', 'page' => 'trang'];
$rows = array_merge(
    array_map(fn($r) => $r + ['type' => 'category', 'tbl' => 'categories'], Db::all('SELECT id, slug FROM categories ORDER BY id')),
    array_map(fn($r) => $r + ['type' => 'product', 'tbl' => 'products'], Db::all('SELECT id, slug FROM products ORDER BY id')),
    array_map(fn($r) => $r + ['type' => $r['kind'], 'tbl' => 'contents'], Db::all("SELECT id, slug, kind FROM contents WHERE kind = 'blog' ORDER BY id")),
    array_map(fn($r) => $r + ['type' => $r['kind'], 'tbl' => 'contents'], Db::all("SELECT id, slug, kind FROM contents WHERE kind = 'page' ORDER BY id")),
);

$seen = [];
$renamed = [];
foreach ($rows as $r) {
    $slug = (string)$r['slug'];
    if (!Urls::isReserved($slug) && !isset($seen[$slug])) { $seen[$slug] = true; continue; }
    Db::tx(function () use ($r, $slug, $suffix, &$seen, &$renamed) {
        $new = Urls::unique($slug . '-' . $suffix[$r['type']], $r['type'], (int)$r['id']);
        Db::exec("UPDATE {$r['tbl']} SET slug = :n WHERE id = :id", ['n' => $new, 'id' => (int)$r['id']]);
        Db::exec('INSERT IGNORE INTO url_aliases (old_path, entity_type, entity_id, created_at) VALUES (:p, :t, :id, :c)',
            ['p' => Urls::LEGACY_PREFIX[$r['type']] . $slug, 't' => $r['type'], 'id' => (int)$r['id'], 'c' => Clock::nowDb()]);
        if ($r['type'] === 'product') \App\Domain\SyncService::emitProduct((int)$r['id']);
        Audit::log('url.slug_renamed', $r['type'], (string)$r['id'], ['slug' => $slug], ['slug' => $new], 'Chuyển sang địa chỉ một cấp .html: trùng đường dẫn', 'system');
        $seen[$new] = true;
        $renamed[] = "{$r['type']} #{$r['id']}: $slug → $new";
    });
}

$legal = App\Domain\LegalPages::install();
echo ($renamed ? 'đổi đường dẫn do trùng: ' . implode('; ', $renamed) . '. ' : 'không có đường dẫn trùng. ')
    . 'trang pháp lý: ' . json_encode($legal, JSON_UNESCAPED_UNICODE) . ' ';
