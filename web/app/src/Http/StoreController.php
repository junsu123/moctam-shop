<?php
declare(strict_types=1);

namespace App\Http;

use App\Core\ApiError;
use App\Core\Db;
use App\Core\Http;
use App\Core\Text;
use App\Core\View;
use App\Domain\CatalogService;
use App\Domain\ContentService;
use App\Domain\OrderService;
use App\Domain\PaymentService;
use App\Domain\PromotionService;
use App\Domain\ShippingService;

final class StoreController
{
    private function render(string $view, array $data): string
    {
        $data['categories'] ??= CatalogService::categories();
        return View::render('store/' . $view, $data, 'store/layout');
    }

    public function home(): string
    {
        return $this->render('home', [
            'title' => setting('store_name') . ' — ' . setting('store_tagline'),
            'description' => setting('store_tagline'),
            'flash' => PromotionService::activeFlashSale(),
            'featured' => CatalogService::featured(8),
            'posts' => ContentService::published('blog', 1, 3)['items'],
        ]);
    }

    public function category(string $slug): string
    {
        $cat = Db::one('SELECT * FROM categories WHERE slug = :s AND is_active = 1', ['s' => $slug]);
        if (!$cat) throw ApiError::notFound('Không tìm thấy danh mục.');
        $sort = (string)($_GET['sap-xep'] ?? 'default');
        $res = CatalogService::search('', (int)$cat['id'], (int)($_GET['trang'] ?? 1), 12, $sort);
        return $this->render('listing', [
            'title' => $cat['name'] . ' — ' . setting('store_name'), 'description' => $cat['description'],
            'heading' => $cat['name'], 'intro' => $cat['description'], 'result' => $res, 'sort' => $sort,
            'baseUrl' => '/danh-muc/' . $cat['slug'], 'query' => [], 'activeCat' => (int)$cat['id'],
        ]);
    }

    public function search(): string
    {
        $q = mb_substr(trim((string)($_GET['q'] ?? '')), 0, 100);
        $res = CatalogService::search($q, null, (int)($_GET['trang'] ?? 1), 12);
        return $this->render('listing', [
            'title' => 'Tìm "' . $q . '" — ' . setting('store_name'), 'description' => '', 'robots' => 'noindex',
            'heading' => $q === '' ? 'Tất cả sản phẩm' : 'Kết quả cho "' . $q . '"',
            'intro' => $res['total'] . ' sản phẩm', 'result' => $res, 'sort' => 'default',
            'baseUrl' => '/tim-kiem', 'query' => ['q' => $q], 'q' => $q,
        ]);
    }

    public function flashSale(): string
    {
        $fs = PromotionService::activeFlashSale();
        return $this->render('flash', ['title' => 'Flash Sale — ' . setting('store_name'), 'description' => 'Giá ưu đãi có thời hạn', 'flash' => $fs]);
    }

    public function product(string $slug): string
    {
        $p = CatalogService::productBySlug($slug);
        if (!$p) {
            $old = Db::one("SELECT slug FROM products WHERE slug = :s AND status = 'discontinued'", ['s' => $slug]);
            throw ApiError::notFound($old ? 'Sản phẩm này đã ngừng bán.' : 'Không tìm thấy sản phẩm.');
        }
        return $this->render('product', [
            'title' => $p['name'] . ' — ' . setting('store_name'),
            'description' => $p['short_desc'] ?: Text::excerpt((string)$p['description'], 155),
            'ogImage' => $p['images'][0]['path'] ?? null, 'p' => $p,
            'faqs' => Db::all("SELECT slug, pub_title, pub_body FROM contents WHERE kind = 'faq' AND status = 'published' AND (product_id = :p OR category_id = :c) LIMIT 4", ['p' => $p['id'], 'c' => $p['category_id']]),
        ]);
    }

    public function cart(): string
    {
        return $this->render('cart', ['title' => 'Giỏ hàng', 'robots' => 'noindex', 'provinces' => ShippingService::servedProvinces()]);
    }

    public function checkout(): string
    {
        return $this->render('checkout', ['title' => 'Thanh toán', 'robots' => 'noindex', 'provinces' => ShippingService::servedProvinces()]);
    }

    /** Xác nhận đơn: trong phiên đặt hàng, hoặc qua liên kết có mã truy cập. */
    public function orderConfirm(string $code): string
    {
        $o = Db::one('SELECT id, code, access_token FROM orders WHERE code = :c', ['c' => strtoupper($code)]);
        $token = (string)($_GET['t'] ?? '');
        $inSession = !empty($_SESSION['my_orders'][$o['code'] ?? '']);
        if (!$o || (!$inSession && !hash_equals($o['access_token'], $token))) {
            throw ApiError::notFound('Không tìm thấy đơn hàng hoặc liên kết đã hết hiệu lực.');
        }
        PaymentService::markQrViewed((int)$o['id']); // chỉ ghi nhận bước hiển thị, KHÔNG phải xác nhận tiền
        return $this->render('order', ['title' => 'Đơn ' . $o['code'], 'robots' => 'noindex', 'order' => OrderService::publicSummary((int)$o['id'])]);
    }

    public function blogIndex(): string
    {
        return $this->render('blog_index', ['title' => 'Blog — ' . setting('store_name'), 'description' => 'Cách pha, bảo quản và câu chuyện nguyên liệu.', 'result' => ContentService::published('blog', (int)($_GET['trang'] ?? 1), 9)]);
    }

    public function blogShow(string $slug): string
    {
        $c = ContentService::bySlug('blog', $slug);
        if (!$c) throw ApiError::notFound('Bài viết không tồn tại hoặc đã được gỡ.');
        $related = $c['product_id'] ? CatalogService::attachFlash(Db::all("SELECT p.id, p.name, p.slug, p.short_desc, (SELECT MIN(price) FROM skus s WHERE s.product_id = p.id AND s.status='active') AS min_price, (SELECT path FROM product_images im WHERE im.product_id = p.id ORDER BY sort_order LIMIT 1) AS image, 1 AS available FROM products p WHERE p.id = :id AND p.status = 'active'", ['id' => $c['product_id']])) : [];
        return $this->render('blog_show', ['title' => $c['pub_title'], 'description' => $c['pub_meta_description'], 'c' => $c, 'related' => $related, 'ogType' => 'article']);
    }

    public function faq(): string
    {
        return $this->render('faq', ['title' => 'Hỏi đáp — ' . setting('store_name'), 'description' => 'Câu hỏi thường gặp về giao hàng, thanh toán, đổi trả và sản phẩm.', 'faqs' => ContentService::published('faq', 1, 200)['items']]);
    }

    public function page(string $slug): string
    {
        $c = ContentService::bySlug('page', $slug);
        if (!$c) throw ApiError::notFound('Không tìm thấy trang.');
        return $this->render('static', ['title' => $c['pub_title'], 'description' => $c['pub_meta_description'], 'c' => $c]);
    }

    public function sitemap(): void
    {
        $base = rtrim((string)config('base_url'), '/');
        $urls = ['/', '/blog', '/hoi-dap'];
        foreach (Db::all('SELECT slug FROM categories WHERE is_active = 1') as $r) $urls[] = '/danh-muc/' . $r['slug'];
        foreach (Db::all("SELECT slug FROM products WHERE status = 'active'") as $r) $urls[] = '/san-pham/' . $r['slug'];
        foreach (Db::all("SELECT kind, slug FROM contents WHERE status = 'published' AND kind IN ('blog','page')") as $r) $urls[] = ($r['kind'] === 'blog' ? '/blog/' : '/chinh-sach/') . $r['slug'];
        header('Content-Type: application/xml; charset=utf-8');
        echo '<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">';
        foreach ($urls as $u) echo '<url><loc>' . e($base . $u) . '</loc></url>';
        echo '</urlset>';
        exit;
    }
}
