<?php
declare(strict_types=1);

namespace App\Domain;

use App\Core\Text;

/**
 * Dữ liệu có cấu trúc (schema.org JSON-LD) và mô tả trang cho công cụ tìm kiếm.
 * Chỉ khai báo điều có thật trên trang: không có đánh giá/sao vì website chưa có chức năng đánh giá,
 * không có chính sách đổi trả dạng số ngày vì chưa có cấu hình tương ứng.
 */
final class Seo
{
    public const DESC_MAX = 160;
    public const TITLE_MAX = 60;

    /** Văn bản thuần từ HTML: thêm khoảng trắng ở ranh giới khối để chữ các đoạn không dính nhau. */
    public static function plain(string $html, int $max = 5000): string
    {
        $html = preg_replace('#<(br|/p|/li|/h[1-6]|/div|/tr|/td|/blockquote)\b[^>]*>#i', '$0 ', $html) ?? $html;
        return Text::excerpt($html, $max);
    }

    public static function abs(string $path): string
    {
        if (preg_match('#^https?://#', $path)) return $path;
        return rtrim((string)config('base_url'), '/') . '/' . ltrim($path, '/');
    }

    /** Ghép các ý thành mô tả ≤ 160 ký tự, cắt ở ranh giới từ. Ý rỗng bị bỏ qua. */
    public static function description(?string ...$parts): string
    {
        $parts = array_values(array_filter(array_map(fn($p) => self::plain((string)$p, 1000), $parts), fn($p) => $p !== ''));
        $out = '';
        foreach ($parts as $p) {
            if (!preg_match('/[.!?…:]$/u', $out) && $out !== '') $out .= '.';
            $try = trim($out . ' ' . $p);
            if (mb_strlen($try) > self::DESC_MAX) {
                if ($out === '') $out = self::clip($p, self::DESC_MAX);
                break;
            }
            $out = $try;
        }
        return $out;
    }

    /** Tiêu đề ≤ 60 ký tự: "Phần chính — Tên xưởng"; quá dài thì bỏ tên xưởng, rồi cắt ở ranh giới từ. */
    public static function title(string $main, ?string $store = null): string
    {
        $store ??= (string)setting('store_name');
        $main = trim($main);
        if ($store === '' || $main === $store || str_contains($main, $store)) return self::clip($main, self::TITLE_MAX);
        $full = $main . ' — ' . $store;
        return mb_strlen($full) <= self::TITLE_MAX ? $full : self::clip($main, self::TITLE_MAX);
    }

    public static function clip(string $s, int $max): string
    {
        $s = trim($s);
        if (mb_strlen($s) <= $max) return $s;
        $cut = mb_substr($s, 0, $max - 1);
        $sp = mb_strrpos($cut, ' ');
        if ($sp !== false && $sp > $max * 0.6) $cut = mb_substr($cut, 0, $sp);
        return rtrim($cut, " ,;:-—–") . '…';
    }

    // ------------------------------------------------------------------ schema.org

    public static function organization(): array
    {
        $o = ['@type' => 'Organization', '@id' => self::abs('/#to-chuc'), 'name' => setting('store_name'), 'url' => self::abs('/'),
              'logo' => ['@type' => 'ImageObject', 'url' => self::abs('/assets/img/logo-512.png'), 'width' => 512, 'height' => 512]];
        if ($v = trim((string)setting('business_name'))) $o['legalName'] = $v;
        if ($v = trim((string)setting('support_email'))) $o['email'] = $v;
        $contact = ['@type' => 'ContactPoint', 'contactType' => 'customer service', 'areaServed' => 'VN', 'availableLanguage' => 'vi'];
        if ($v = trim((string)setting('hotline'))) { $o['telephone'] = $v; $contact['telephone'] = $v; }
        if (isset($contact['telephone'])) $o['contactPoint'] = [$contact];
        $addr = trim((string)setting('address'));
        if ($addr !== '' && !str_contains(mb_strtolower($addr), 'cập nhật')) $o['address'] = ['@type' => 'PostalAddress', 'streetAddress' => $addr, 'addressCountry' => 'VN'];
        if ($z = preg_replace('/\D/', '', (string)setting('zalo'))) $o['sameAs'] = ['https://zalo.me/' . $z];
        return $o;
    }

    public static function website(): array
    {
        return ['@type' => 'WebSite', '@id' => self::abs('/#website'), 'name' => setting('store_name'), 'url' => self::abs('/'),
                'inLanguage' => 'vi-VN', 'publisher' => ['@id' => self::abs('/#to-chuc')]];
    }

    /** @param array<array{0:string,1:string}> $items [[tên, đường dẫn], …] — bắt đầu từ Trang chủ */
    public static function breadcrumbs(array $items): array
    {
        $list = [];
        foreach (array_values($items) as $i => [$name, $path]) {
            $list[] = ['@type' => 'ListItem', 'position' => $i + 1, 'name' => $name, 'item' => self::abs($path)];
        }
        return ['@type' => 'BreadcrumbList', 'itemListElement' => $list];
    }

    /** Sản phẩm: mỗi quy cách (SKU) là một Offer với giá thực bán (gồm Flash Sale) và tình trạng còn hàng. */
    public static function product(array $p): array
    {
        $url = self::abs(Urls::to($p['slug']));
        $offers = [];
        foreach ($p['skus'] as $s) {
            $price = $s['sale_price'] ?? $s['price'];
            $o = ['@type' => 'Offer', 'sku' => $s['sku_code'], 'name' => trim($p['name'] . ' – ' . $s['variant_label']), 'url' => $url,
                  'price' => (string)(int)$price, 'priceCurrency' => 'VND', 'itemCondition' => 'https://schema.org/NewCondition',
                  'availability' => 'https://schema.org/' . ((int)$s['available'] > 0 ? 'InStock' : 'OutOfStock'),
                  'seller' => ['@id' => self::abs('/#to-chuc')]];
            if (!empty($s['sale_price']) && !empty($s['flash_ends_at'])) {
                $o['priceValidUntil'] = substr(\App\Core\Clock::toLocal($s['flash_ends_at'])->format('c'), 0, 10);
            }
            if (!empty($s['net_weight_g'])) $o['weight'] = ['@type' => 'QuantitativeValue', 'value' => (int)$s['net_weight_g'], 'unitCode' => 'GRM'];
            $offers[] = $o;
        }
        $node = ['@type' => 'Product', '@id' => $url . '#san-pham', 'name' => $p['name'], 'url' => $url,
                 'description' => self::plain((string)($p['description'] ?: $p['short_desc'])),
                 'brand' => ['@type' => 'Brand', 'name' => setting('store_name')], 'category' => $p['category_name'] ?? null,
                 'image' => array_map(fn($i) => self::abs($i['path']), $p['images'] ?? [])];
        if (count($p['skus']) === 1) $node['sku'] = $p['skus'][0]['sku_code'];
        if ($offers) $node['offers'] = count($offers) === 1 ? $offers[0] : $offers;
        return array_filter($node, fn($v) => $v !== null && $v !== []);
    }

    public static function article(array $c, string $path): array
    {
        $a = ['@type' => 'BlogPosting', '@id' => self::abs($path) . '#bai-viet', 'headline' => self::clip((string)$c['pub_title'], 110),
              'description' => (string)($c['pub_meta_description'] ?? ''), 'mainEntityOfPage' => self::abs($path), 'inLanguage' => 'vi-VN',
              'author' => ['@id' => self::abs('/#to-chuc')], 'publisher' => ['@id' => self::abs('/#to-chuc')]];
        if (!empty($c['published_at'])) $a['datePublished'] = \App\Core\Clock::toLocal($c['published_at'])->format('c');
        if (!empty($c['updated_at'])) $a['dateModified'] = \App\Core\Clock::toLocal(max($c['updated_at'], $c['published_at'] ?? ''))->format('c');
        $a['image'] = [self::abs(self::articleImage($c) ?? '/assets/img/og-mac-dinh.png')]; // Google cần ảnh cho kết quả dạng bài viết
        return array_filter($a, fn($v) => $v !== '');
    }

    /** Ảnh đại diện bài viết: ảnh bìa, không có thì ảnh đầu tiên trong bài. */
    public static function articleImage(array $c): ?string
    {
        if (!empty($c['cover_image'])) return $c['cover_image'];
        return preg_match('/<img[^>]+src="([^"]+)"/i', (string)($c['pub_body'] ?? ''), $m) ? html_entity_decode($m[1]) : null;
    }

    /** @param array $faqs danh sách có pub_title, pub_body */
    public static function faqPage(array $faqs, string $path): array
    {
        return ['@type' => 'FAQPage', '@id' => self::abs($path) . '#hoi-dap', 'mainEntity' => array_map(fn($f) => [
            '@type' => 'Question', 'name' => (string)$f['pub_title'],
            'acceptedAnswer' => ['@type' => 'Answer', 'text' => self::plain((string)$f['pub_body'])],
        ], $faqs)];
    }

    /** Thẻ <script type="application/ld+json"> an toàn (JSON_HEX_TAG chặn "</script>" trong dữ liệu). */
    public static function script(array $nodes): string
    {
        $nodes = array_values(array_filter($nodes));
        if (!$nodes) return '';
        $json = json_encode(['@context' => 'https://schema.org', '@graph' => $nodes],
            JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES | JSON_HEX_TAG | JSON_HEX_AMP | JSON_PRETTY_PRINT);
        return '<script type="application/ld+json">' . $json . '</script>';
    }
}
