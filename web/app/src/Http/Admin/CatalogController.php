<?php
declare(strict_types=1);

namespace App\Http\Admin;

use App\Core\ApiError;
use App\Core\Audit;
use App\Core\Db;
use App\Core\Http;
use App\Core\Text;
use App\Domain\CatalogService;

final class CatalogController extends Base
{
    public function index(): string
    {
        $this->need('catalog.manage');
        $where = ['1=1'];
        $p = [];
        if (($q = $this->str('q')) !== '') { $where[] = 'p.search_text LIKE :q'; $p['q'] = '%' . Text::fold($q) . '%'; }
        if ($c = $this->int('category')) { $where[] = 'p.category_id = :c'; $p['c'] = $c; }
        if (($st = $this->str('status')) !== '') { $where[] = 'p.status = :s'; $p['s'] = $st; }
        $rows = Db::all('SELECT p.*, c.name AS cat, (SELECT COUNT(*) FROM skus s WHERE s.product_id = p.id) AS sku_count,
                           (SELECT MIN(price) FROM skus s WHERE s.product_id = p.id AND s.status = \'active\') AS min_price,
                           (SELECT path FROM product_images im WHERE im.product_id = p.id ORDER BY sort_order LIMIT 1) AS image
                         FROM products p JOIN categories c ON c.id = p.category_id WHERE ' . implode(' AND ', $where) . ' ORDER BY p.updated_at DESC', $p);
        return $this->view('products', ['title' => 'Sản phẩm', 'rows' => $rows, 'cats' => Db::all('SELECT id, name FROM categories ORDER BY sort_order'), 'f' => $_GET]);
    }

    public function create(): string
    {
        $this->need('catalog.manage');
        return $this->form(null);
    }

    public function edit(string $id): string
    {
        $this->need('catalog.manage');
        return $this->form((int)$id);
    }

    private function form(?int $id): string
    {
        $p = $id ? Db::one('SELECT * FROM products WHERE id = :id', ['id' => $id]) : null;
        if ($id && !$p) throw ApiError::notFound();
        return $this->view('product_form', [
            'title' => $p ? $p['name'] : 'Thêm sản phẩm',
            'p' => $p,
            'cats' => Db::all('SELECT id, name FROM categories ORDER BY sort_order'),
            'skus' => $id ? Db::all('SELECT s.*, i.on_hand, i.reserved FROM skus s LEFT JOIN inventory i ON i.sku_id = s.id WHERE s.product_id = :id ORDER BY s.sort_order, s.id', ['id' => $id]) : [],
            'images' => $id ? Db::all('SELECT * FROM product_images WHERE product_id = :id ORDER BY sort_order', ['id' => $id]) : [],
            'relations' => $id ? Db::all('SELECT r.*, p2.name FROM product_relations r JOIN products p2 ON p2.id = r.related_product_id WHERE r.product_id = :id ORDER BY r.sort_order', ['id' => $id]) : [],
            'allProducts' => Db::all("SELECT id, name FROM products WHERE status <> 'discontinued' ORDER BY name"),
        ]);
    }

    public function save(): never
    {
        $id = $this->int('id') ?: null;
        $newId = CatalogService::saveProduct($id, $_POST);
        $this->back($id ? 'Đã lưu sản phẩm.' : 'Đã tạo sản phẩm. Thêm quy cách (SKU) và ảnh bên dưới.', '/admin/products/' . $newId);
    }

    public function sku(string $id): never
    {
        CatalogService::saveSku((int)$id, $this->int('sku_id') ?: null, $_POST);
        $this->back('Đã lưu quy cách.');
    }

    public function image(string $id): never
    {
        CatalogService::addImage((int)$id, $_FILES['image'] ?? [], $this->str('alt'));
        $this->back('Đã thêm ảnh.');
    }

    public function imageDelete(string $id): never
    {
        $this->need('catalog.manage');
        $img = Db::one('SELECT * FROM product_images WHERE id = :i AND product_id = :p', ['i' => $this->int('image_id'), 'p' => (int)$id]);
        if ($img) {
            Db::exec('DELETE FROM product_images WHERE id = :i', ['i' => $img['id']]);
            if (str_starts_with($img['path'], '/uploads/')) @unlink(rtrim((string)config('paths.uploads'), '/') . substr($img['path'], 8));
            Audit::log('product.image_delete', 'product', $id, ['path' => $img['path']]);
        }
        $this->back('Đã xóa ảnh.');
    }

    public function relation(string $id): never
    {
        if ($this->str('remove')) {
            $this->need('catalog.manage');
            Db::exec('DELETE FROM product_relations WHERE id = :r AND product_id = :p', ['r' => $this->int('relation_id'), 'p' => (int)$id]);
            Audit::log('crosssell.remove', 'product', $id, null, ['relation' => $this->int('relation_id')]);
            $this->back('Đã bỏ gợi ý.');
        }
        CatalogService::saveRelation((int)$id, $this->int('related_product_id'));
        $this->back('Đã thêm sản phẩm mua kèm.');
    }

    public function delete(string $id): never
    {
        $r = CatalogService::deleteOrDiscontinue((int)$id);
        $this->back($r === 'deleted' ? 'Đã xóa sản phẩm.' : 'Sản phẩm đã có trong đơn nên được chuyển sang Ngừng bán (giữ lịch sử).', '/admin/products');
    }

    public function categories(): string
    {
        $this->need('catalog.manage');
        return $this->view('categories', ['title' => 'Danh mục', 'rows' => Db::all('SELECT c.*, (SELECT COUNT(*) FROM products p WHERE p.category_id = c.id) AS n FROM categories c ORDER BY sort_order, id')]);
    }

    public function saveCategory(): never
    {
        $this->need('catalog.manage');
        $id = $this->int('id');
        $data = [
            'name' => mb_substr($this->str('name'), 0, 120), 'description' => mb_substr($this->str('description'), 0, 500) ?: null,
            'repurchase_days' => $this->str('repurchase_days') === '' ? null : max(1, $this->int('repurchase_days')),
            'sort_order' => $this->int('sort_order'), 'is_active' => $this->str('is_active') ? 1 : 0,
        ];
        if (mb_strlen($data['name']) < 2) throw ApiError::validation(['name' => 'Bắt buộc']);
        if ($id) {
            $before = Db::one('SELECT * FROM categories WHERE id = :id', ['id' => $id]);
            Db::update('categories', $data, 'id = :id', ['id' => $id]);
            Audit::log('category.update', 'category', (string)$id, $before, $data);
        } else {
            $slug = Text::slug($data['name']);
            if (Db::val('SELECT 1 FROM categories WHERE slug = :s', ['s' => $slug])) $slug .= '-' . substr(bin2hex(random_bytes(2)), 0, 3);
            $id = Db::insert('categories', $data + ['slug' => $slug]);
            Audit::log('category.create', 'category', (string)$id, null, $data);
        }
        $this->back('Đã lưu danh mục.');
    }

    public function crosssell(): string
    {
        $this->need('crosssell.review');
        $rows = Db::all("SELECT r.*, a.name AS a_name, a.slug AS a_slug, b.name AS b_name, b.slug AS b_slug FROM product_relations r JOIN products a ON a.id = r.product_id JOIN products b ON b.id = r.related_product_id
                         ORDER BY FIELD(r.status,'pending','approved','rejected'), r.score DESC, r.id DESC LIMIT 200");
        return $this->view('crosssell', ['title' => 'Gợi ý mua kèm', 'rows' => $rows]);
    }

    public function reviewCrosssell(string $id): never
    {
        CatalogService::reviewRelation((int)$id, $this->str('decision') === 'approve');
        $this->back('Đã cập nhật gợi ý.');
    }
}
