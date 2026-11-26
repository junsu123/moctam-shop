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
            'title' => \App\Domain\Seo::title(setting('store_name') . ' — ' . setting('store_tagline')),
            'description' => \App\Domain\Seo::description(setting('store_name') . ': ' . setting('store_tagline'), 'Đặt hàng online, thanh toán khi nhận hàng (COD) hoặc chuyển khoản VietQR', 'Hotline ' . setting('hotline')),
            'jsonLd' => [\App\Domain\Seo::organization(), \App\Domain\Seo::website()],
            'flash' => PromotionService::activeFlashSale(),
            'featured' => CatalogService::featured(8),
            'posts' => ContentService::published('blog', 1, 3)['items'],
        ]);
    }

    /** "24 sản phẩm trà túi lọc, giá từ 45.000 ₫" — số liệu thật của danh mục cho mô tả trang */
    private function categorySummary(int $catId, string $name): string
    {
        $r = Db::one("SELECT COUNT(DISTINCT p.id) n, MIN(s.price) mn FROM products p JOIN skus s ON s.product_id = p.id AND s.status = 'active' WHERE p.category_id = :c AND p.status = 'active'", ['c' => $catId]);
        if (!$r || !(int)$r['n']) return '';
        return (int)$r['n'] . ' sản phẩm ' . mb_strtolower($name) . ', giá từ ' . money((int)$r['mn']);
    }

    /** "Hộp 20 túi, Hộp 50 túi — giá từ 45.000 ₫" */
    private function productSummary(array $p): string
    {
        if (!$p['skus']) return '';
        $prices = array_map(fn($s) => (int)($s['sale_price'] ?? $s['price']), $p['skus']);
        $labels = implode(', ', array_slice(array_column($p['skus'], 'variant_label'), 0, 3));
        return $labels . ' — giá ' . (count($p['skus']) > 1 ? 'từ ' : '') . money(min($prices));
    }

    /** /{slug}.html → danh mục, sản phẩm, bài blog hoặc trang chính sách (Urls::resolve). */
    public function resolve(string $slug): string
    {
        $hit = \App\Domain\Urls::resolve($slug);
        return match ($hit['type'] ?? null) {
            'category' => $this->category($slug),
            'product' => $this->product($slug),
            'blog' => $this->blogShow($slug),
            'page' => $this->page($slug),
            default => throw ApiError::notFound('Không tìm thấy trang.'),
        };
    }

    public function category(string $slug): string
    {
        $cat = Db::one('SELECT * FROM categories WHERE slug = :s AND is_active = 1', ['s' => $slug]);
        if (!$cat) throw ApiError::notFound('Không tìm thấy danh mục.');
        $sort = (string)($_GET['sap-xep'] ?? 'default');
        $res = CatalogService::search('', (int)$cat['id'], (int)($_GET['trang'] ?? 1), 12, $sort);
        return $this->render('listing', [
            'title' => $cat['name'], 'description' => \App\Domain\Seo::description($cat['description'], $this->categorySummary((int)$cat['id'], $cat['name'])),
            'jsonLd' => [\App\Domain\Seo::breadcrumbs([['Trang chủ', '/'], [$cat['name'], page_url($cat['slug'])]])], 'cardHeading' => 'h2',
            'heading' => $cat['name'], 'intro' => $cat['description'], 'result' => $res, 'sort' => $sort,
            'baseUrl' => page_url($cat['slug']), 'query' => [], 'activeCat' => (int)$cat['id'],
        ]);
    }

    public function search(): string
    {
        $q = mb_substr(trim((string)($_GET['q'] ?? '')), 0, 100);
        $res = CatalogService::search($q, null, (int)($_GET['trang'] ?? 1), 12);
        return $this->render('listing', [
            'title' => 'Tìm "' . $q . '"', 'description' => 'Kết quả tìm kiếm sản phẩm tại ' . setting('store_name') . '.', 'robots' => 'noindex, follow', 'cardHeading' => 'h2',
            'heading' => $q === '' ? 'Tất cả sản phẩm' : 'Kết quả cho "' . $q . '"',
            'intro' => $res['total'] . ' sản phẩm', 'result' => $res, 'sort' => 'default',
            'baseUrl' => fixed_url('search'), 'query' => ['q' => $q], 'q' => $q,
        ]);
    }

    public function flashSale(): string
    {
        $fs = PromotionService::activeFlashSale();
        return $this->render('flash', ['title' => 'Flash Sale', 'description' => \App\Domain\Seo::description('Flash Sale tại ' . setting('store_name') . ': giá ưu đãi có thời hạn cho trà túi lọc, bột ngũ cốc, bột thiên nhiên và cà phê', 'Số lượng có hạn, giá áp dụng đến khi chương trình kết thúc'),
            'jsonLd' => [\App\Domain\Seo::breadcrumbs([['Trang chủ', '/'], ['Flash Sale', fixed_url('flash')]])], 'flash' => $fs]);
    }

    public function product(string $slug): string
    {
        $p = CatalogService::productBySlug($slug);
        if (!$p) {
            $old = Db::one("SELECT slug FROM products WHERE slug = :s AND status = 'discontinued'", ['s' => $slug]);
            throw ApiError::notFound($old ? 'Sản phẩm này đã ngừng bán.' : 'Không tìm thấy sản phẩm.');
        }
        return $this->render('product', [
            'title' => $p['name'],
            'description' => \App\Domain\Seo::description($p['short_desc'] ?: $p['description'], $this->productSummary($p), setting('store_name')),
            'ogImage' => $p['images'][0]['path'] ?? null, 'ogImageAlt' => $p['images'][0]['alt'] ?? $p['name'], 'ogType' => 'product', 'p' => $p,
            'jsonLd' => [\App\Domain\Seo::product($p), \App\Domain\Seo::breadcrumbs([['Trang chủ', '/'], [$p['category_name'], page_url($p['category_slug'])], [$p['name'], page_url($p['slug'])]])],
            'faqs' => Db::all("SELECT slug, pub_title, pub_body FROM contents WHERE kind = 'faq' AND status = 'published' AND (product_id = :p OR category_id = :c) LIMIT 4", ['p' => $p['id'], 'c' => $p['category_id']]),
        ]);
    }

    public function cart(): string
    {
        return $this->render('cart', ['title' => 'Giỏ hàng', 'description' => 'Giỏ hàng của bạn tại ' . setting('store_name') . '.', 'robots' => 'noindex, nofollow', 'provinces' => ShippingService::servedProvinces()]);
    }

    public function checkout(): string
    {
        return $this->render('checkout', ['title' => 'Đặt hàng', 'description' => 'Điền thông tin giao hàng và chọn cách thanh toán.', 'robots' => 'noindex, nofollow', 'provinces' => ShippingService::servedProvinces()]);
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
        return $this->render('order', ['title' => 'Đơn ' . $o['code'], 'robots' => 'noindex, nofollow', 'order' => OrderService::publicSummary((int)$o['id'])]);
    }

    public function blogIndex(): string
    {
        return $this->render('blog_index', ['title' => 'Blog', 'description' => \App\Domain\Seo::description('Blog của ' . setting('store_name') . ': cách pha trà, bảo quản bột ngũ cốc, cà phê và câu chuyện nguyên liệu'),
            'jsonLd' => [\App\Domain\Seo::breadcrumbs([['Trang chủ', '/'], ['Blog', fixed_url('blog')]])], 'result' => ContentService::published('blog', (int)($_GET['trang'] ?? 1), 9)]);
    }

    public function blogShow(string $slug): string
    {
        $c = ContentService::bySlug('blog', $slug);
        if (!$c) throw ApiError::notFound('Bài viết không tồn tại hoặc đã được gỡ.');
        $related = $c['product_id'] ? CatalogService::attachFlash(Db::all("SELECT p.id, p.name, p.slug, p.short_desc, (SELECT MIN(price) FROM skus s WHERE s.product_id = p.id AND s.status='active') AS min_price, (SELECT path FROM product_images im WHERE im.product_id = p.id ORDER BY sort_order LIMIT 1) AS image, 1 AS available FROM products p WHERE p.id = :id AND p.status = 'active'", ['id' => $c['product_id']])) : [];
        return $this->render('blog_show', ['title' => $c['pub_title'], 'description' => \App\Domain\Seo::description($c['pub_meta_description'] ?: $c['pub_body']), 'c' => $c, 'related' => $related, 'ogType' => 'article',
            'ogImage' => \App\Domain\Seo::articleImage($c),
            'jsonLd' => [\App\Domain\Seo::article($c, page_url($c['slug'])), \App\Domain\Seo::breadcrumbs([['Trang chủ', '/'], ['Blog', fixed_url('blog')], [$c['pub_title'], page_url($c['slug'])]])]]);
    }

    public function faq(): string
    {
        return $this->render('faq', ['title' => 'Hỏi đáp', 'description' => \App\Domain\Seo::description('Câu hỏi thường gặp khi mua hàng tại ' . setting('store_name') . ': giao hàng, thanh toán COD/VietQR, đổi trả, cách dùng và bảo quản sản phẩm'),
            'faqs' => $faqs = ContentService::published('faq', 1, 200)['items'],
            'jsonLd' => [\App\Domain\Seo::faqPage($faqs, fixed_url('faq')), \App\Domain\Seo::breadcrumbs([['Trang chủ', '/'], ['Hỏi đáp', fixed_url('faq')]])]]);
    }

    public function page(string $slug): string
    {
        $c = ContentService::bySlug('page', $slug);
        if (!$c) throw ApiError::notFound('Không tìm thấy trang.');
        return $this->render('static', ['title' => $c['pub_title'], 'description' => \App\Domain\Seo::description($c['pub_meta_description'] ?: $c['pub_body']), 'c' => $c,
            'jsonLd' => [\App\Domain\Seo::breadcrumbs([['Trang chủ', '/'], [$c['pub_title'], page_url($c['slug'])]])]]);
    }

    public function sitemap(): void
    {
        header('Content-Type: application/xml; charset=utf-8');
        echo self::sitemapXml();
        exit;
    }

    /** Sitemap kèm lastmod (ngày cập nhật thật) — Google dùng để biết trang nào cần thu thập lại. */
    public static function sitemapXml(): string
    {
        $d = fn(?string $utc) => $utc ? \App\Core\Clock::toLocal($utc)->format('Y-m-d') : null;
        $last = Db::val("SELECT MAX(updated_at) FROM products WHERE status = 'active'");
        $urls = [['/', $d($last)], [fixed_url('flash'), null], [fixed_url('faq'), $d(Db::val("SELECT MAX(COALESCE(published_at, updated_at)) FROM contents WHERE kind = 'faq' AND status = 'published'"))],
                 [fixed_url('blog'), $d(Db::val("SELECT MAX(published_at) FROM contents WHERE kind = 'blog' AND status = 'published'"))]];
        foreach (Db::all("SELECT c.slug, MAX(p.updated_at) m FROM categories c LEFT JOIN products p ON p.category_id = c.id AND p.status = 'active' WHERE c.is_active = 1 GROUP BY c.id, c.slug ORDER BY c.sort_order, c.id") as $r) $urls[] = [page_url($r['slug']), $d($r['m'])];
        foreach (Db::all("SELECT slug, updated_at FROM products WHERE status = 'active' ORDER BY id") as $r) $urls[] = [page_url($r['slug']), $d($r['updated_at'])];
        foreach (Db::all("SELECT slug, GREATEST(COALESCE(published_at, updated_at), updated_at) m FROM contents WHERE status = 'published' AND kind IN ('blog','page') ORDER BY kind, id") as $r) $urls[] = [page_url($r['slug']), $d($r['m'])];
        $x = '<?xml version="1.0" encoding="UTF-8"?>' . "\n" . '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' . "\n";
        foreach ($urls as [$u, $m]) $x .= '<url><loc>' . e(\App\Domain\Seo::abs($u)) . '</loc>' . ($m ? '<lastmod>' . $m . '</lastmod>' : '') . "</url>\n";
        return $x . '</urlset>';
    }

    /**
     * robots.txt: chặn trang không cần lên Google (quản trị, API, giỏ, đặt hàng, tài khoản, kết quả tìm kiếm nội bộ,
     * trang sắp xếp trùng nội dung) và chỉ tới sitemap. Không chặn CSS/JS/ảnh — Google cần để hiển thị trang.
     */
    public static function robotsTxt(): string
    {
        $F = \App\Domain\Urls::FIXED;
        $dis = ['/admin', '/api/', '/auth/', '/tai-khoan', '/' . $F['cart'] . '.html', '/' . $F['checkout'] . '.html', '/' . $F['search'] . '.html',
                '/' . $F['login'] . '.html', '/' . $F['deletion'] . '.html', '/' . \App\Domain\Urls::ORDER_PREFIX, '/*?*sap-xep='];
        return "User-agent: *\n" . implode('', array_map(fn($p) => "Disallow: $p\n", $dis)) . "\nSitemap: " . \App\Domain\Seo::abs('/sitemap.xml') . "\n";
    }

    public function robots(): void
    {
        header('Content-Type: text/plain; charset=utf-8');
        echo self::robotsTxt();
        exit;
    }
}
