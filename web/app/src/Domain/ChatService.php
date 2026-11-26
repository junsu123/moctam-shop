<?php
declare(strict_types=1);

namespace App\Domain;

use App\Core\Clock;
use App\Core\Db;
use App\Core\Settings;
use App\Core\Text;

/**
 * Chat tư vấn trên website (FR-10). Chạy hoàn toàn trên Hostinger, KHÔNG cần máy Python
 * hay LLM (AT-10):
 *   1. Câu hỏi giá / tồn / ưu đãi → đọc dữ liệu HIỆN HÀNH (AT-09).
 *   2. Câu hỏi thành phần / dị ứng / cách dùng / bảo quản → trích nhãn sản phẩm đã duyệt.
 *   3. Còn lại → FAQ đã xuất bản (BM25, ngưỡng cấu hình được).
 *   4. Không đủ tin cậy → hiện kênh hỗ trợ của xưởng.
 */
final class ChatService
{
    private const INTENTS = [
        'price'   => ['gia', 'bao nhieu tien', 'bao nhieu', 'tien', 'mac khong', 're khong'],
        'stock'   => ['con hang', 'het hang', 'con khong', 'co san', 'ton kho', 'con ban'],
        'promo'   => ['khuyen mai', 'giam gia', 'voucher', 'ma giam', 'flash sale', 'uu dai', 'sale'],
        'label'   => ['thanh phan', 'di ung', 'cach dung', 'cach pha', 'bao quan', 'han dung', 'su dung', 'pha the nao', 'gluten', 'sua', 'dau phong', 'duong'],
        'order'   => ['don hang', 'ma don', 'kiem tra don', 'tra cuu don', 'giao toi dau', 'van don'],
    ];

    public static function answer(string $message): array
    {
        $message = mb_substr(trim($message), 0, 500);
        $folded = ' ' . Text::fold($message) . ' ';
        $intents = [];
        foreach (self::INTENTS as $intent => $phrases) {
            foreach ($phrases as $p) {
                if (str_contains($folded, ' ' . $p . ' ')) {
                    $intents[$intent] = true;
                    break;
                }
            }
        }
        $support = self::support();

        if ($folded === '  ') {
            return self::reply('Bạn cần tư vấn sản phẩm nào ạ? Mình có thể báo giá, tình trạng hàng, ưu đãi và cách dùng.', 'fallback', $message);
        }

        // Tra cứu đơn: không tiết lộ thông tin đơn qua chat (không xác thực danh tính)
        if (isset($intents['order'])) {
            return self::reply("Để bảo mật, bạn xem trạng thái đơn qua đường dẫn trong trang xác nhận đơn, hoặc liên hệ xưởng: hotline {$support['hotline']}, Zalo {$support['zalo']}.", 'fallback', $message, ['support' => $support]);
        }

        // Bỏ cụm từ chỉ ý định trước khi dò sản phẩm để điểm khớp tên sản phẩm không bị pha loãng
        $cleaned = $folded;
        foreach (self::INTENTS as $phrases) {
            foreach ($phrases as $p) {
                $cleaned = str_replace(' ' . $p . ' ', ' ', $cleaned);
            }
        }
        $cleaned = str_replace([' co ', ' khong ', ' con ', ' loai ', ' nay ', ' bao ', ' nhieu '], ' ', $cleaned);
        $products = self::findProducts($cleaned);
        $needsLive = isset($intents['price']) || isset($intents['stock']) || isset($intents['promo']);

        // 1) Giá / tồn / ưu đãi — dữ liệu hiện hành
        if ($needsLive && $products) {
            $cards = array_map([self::class, 'liveCard'], array_slice($products, 0, 2));
            $lines = [];
            foreach ($cards as $c) {
                $parts = [];
                foreach ($c['skus'] as $s) {
                    $price = $s['sale_price'] !== null ? money($s['sale_price']) . ' (Flash Sale, giá thường ' . money($s['price']) . ')' : money($s['price']);
                    $stock = $s['available'] > 0 ? ($s['available'] <= 5 ? "còn {$s['available']}" : 'còn hàng') : 'tạm hết';
                    $parts[] = "{$s['variant_label']}: $price — $stock";
                }
                $lines[] = "• {$c['name']}: " . implode('; ', $parts);
            }
            $text = "Thông tin hiện tại:\n" . implode("\n", $lines);
            if (isset($intents['promo'])) {
                $text .= "\n" . self::promoText();
            }
            $text .= "\nGiá cuối cùng được xác nhận ở bước thanh toán.";
            return self::reply($text, 'live', $message, ['products' => $cards, 'suggestions' => self::crossSell((int)$products[0]['id'])]);
        }
        if (isset($intents['promo']) && !$products) {
            return self::reply(self::promoText(), 'live', $message);
        }

        // 2) Nhãn sản phẩm đã duyệt
        if (isset($intents['label']) && $products) {
            $p = Db::one('SELECT id, name, slug, ingredients, usage_guide, storage_guide, allergens FROM products WHERE id = :id', ['id' => $products[0]['id']]);
            $f = ' ' . Text::fold($message) . ' ';
            $field = match (true) {
                str_contains($f, ' di ung ') || str_contains($f, ' gluten ') || str_contains($f, ' dau phong ') || str_contains($f, ' sua ') => ['allergens', 'Thông tin dị ứng'],
                str_contains($f, ' bao quan ') || str_contains($f, ' han dung ') => ['storage_guide', 'Bảo quản'],
                str_contains($f, ' cach dung ') || str_contains($f, ' cach pha ') || str_contains($f, ' su dung ') || str_contains($f, ' pha the nao ') => ['usage_guide', 'Cách dùng'],
                default => ['ingredients', 'Thành phần'],
            };
            $val = trim((string)$p[$field[0]]);
            if ($val !== '') {
                return self::reply("{$field[1]} của {$p['name']} (theo nhãn sản phẩm):\n$val", 'label', $message, ['products' => [self::liveCard($products[0])]]);
            }
            return self::reply("Xưởng chưa cập nhật mục \"{$field[1]}\" cho {$p['name']} trên website. Bạn vui lòng liên hệ hotline {$support['hotline']} hoặc Zalo {$support['zalo']} để được tư vấn chính xác.", 'fallback', $message, ['support' => $support]);
        }

        // 3) FAQ đã duyệt
        $faqs = Db::all("SELECT id, pub_title, pub_body, pub_search_text, product_id FROM contents WHERE kind = 'faq' AND status = 'published'");
        if ($faqs) {
            $docs = [];
            foreach ($faqs as $f) {
                $docs[$f['id']] = $f['pub_title'] . ' ' . $f['pub_title'] . ' ' . $f['pub_search_text'];
            }
            $ranked = Bm25::rank($message, $docs);
            $bestId = array_key_first($ranked);
            $threshold = (float)Settings::get('chat_faq_threshold', '0.10');
            if ($bestId !== null && $ranked[$bestId] >= $threshold) {
                $faq = array_values(array_filter($faqs, fn($f) => (int)$f['id'] === (int)$bestId))[0];
                $extra = ['faq' => ['id' => (int)$faq['id'], 'question' => $faq['pub_title']], 'score' => round($ranked[$bestId], 4)];
                $pid = $faq['product_id'] ? (int)$faq['product_id'] : ($products[0]['id'] ?? null);
                if ($pid) $extra['suggestions'] = self::crossSell((int)$pid);
                return self::reply(Text::excerpt($faq['pub_body'], 900), 'faq', $message, $extra, (int)$faq['id'], $ranked[$bestId]);
            }
        }

        // Có nhắc sản phẩm nhưng không rõ ý → giới thiệu sản phẩm với dữ liệu hiện hành
        if ($products) {
            $cards = array_map([self::class, 'liveCard'], array_slice($products, 0, 3));
            return self::reply('Mình tìm thấy các sản phẩm sau, bạn bấm vào để xem quy cách và giá hiện tại nhé. Nếu cần tư vấn thêm, gọi hotline ' . $support['hotline'] . '.', 'live', $message, ['products' => $cards]);
        }

        // 4) Không có câu trả lời phù hợp
        return self::reply("Câu này mình chưa có câu trả lời chính xác. Bạn liên hệ xưởng để được hỗ trợ nhanh nhất: hotline {$support['hotline']}, Zalo {$support['zalo']}, email {$support['email']}.", 'fallback', $message, ['support' => $support]);
    }

    private static function findProducts(string $message): array
    {
        $tokens = array_values(array_filter(Text::tokens($message), fn($t) => strlen($t) >= 2));
        if (!$tokens) return [];
        $rows = Db::all("SELECT id, name, slug, search_text FROM products WHERE status = 'active'");
        $docs = [];
        foreach ($rows as $r) {
            $docs[$r['id']] = $r['name'] . ' ' . $r['name'] . ' ' . $r['search_text'];
        }
        $ranked = Bm25::rank($message, $docs);
        $out = [];
        foreach ($ranked as $id => $score) {
            if ($score < 0.18) break;
            foreach ($rows as $r) {
                if ((int)$r['id'] === (int)$id) $out[] = $r + ['score' => $score];
            }
            if (count($out) >= 3) break;
        }
        return $out;
    }

    private static function liveCard(array $p): array
    {
        $skus = Db::all("SELECT s.id, s.variant_label, s.price, GREATEST(COALESCE(i.on_hand,0) - COALESCE(i.reserved,0),0) AS available FROM skus s LEFT JOIN inventory i ON i.sku_id = s.id WHERE s.product_id = :id AND s.status = 'active' ORDER BY s.sort_order, s.id", ['id' => $p['id']]);
        $flash = PricingService::activeFlashPrices(array_column($skus, 'id'));
        return [
            'id' => (int)$p['id'], 'name' => $p['name'], 'url' => Urls::to($p['slug']),
            'skus' => array_map(fn($s) => ['sku_id' => (int)$s['id'], 'variant_label' => $s['variant_label'], 'price' => (int)$s['price'],
                'sale_price' => isset($flash[$s['id']]) ? (int)$flash[$s['id']]['sale_price'] : null, 'available' => (int)$s['available']], $skus),
        ];
    }

    private static function crossSell(int $productId): array
    {
        return array_map(fn($r) => ['name' => $r['name'], 'url' => Urls::to($r['slug'])], Db::all(
            "SELECT p.name, p.slug FROM product_relations r JOIN products p ON p.id = r.related_product_id WHERE r.product_id = :id AND r.status = 'approved' AND p.status = 'active' ORDER BY r.sort_order LIMIT 3",
            ['id' => $productId]
        ));
    }

    private static function promoText(): string
    {
        $now = Clock::nowDb();
        $parts = [];
        $fs = PromotionService::activeFlashSale();
        if ($fs) {
            $parts[] = "Flash Sale \"{$fs['name']}\" đang diễn ra đến " . vn_time($fs['ends_at'], 'H:i d/m') . ' (' . count($fs['items']) . ' sản phẩm).';
        }
        $vs = Db::all('SELECT code, amount, min_subtotal FROM vouchers WHERE is_active = 1 AND starts_at <= :n AND ends_at > :n2 AND (usage_limit IS NULL OR reserved_count + used_count < usage_limit) ORDER BY amount DESC LIMIT 3', ['n' => $now, 'n2' => $now]);
        foreach ($vs as $v) {
            $parts[] = "Mã {$v['code']}: giảm " . money($v['amount']) . ((int)$v['min_subtotal'] > 0 ? ' cho đơn từ ' . money($v['min_subtotal']) : '') . '.';
        }
        return $parts ? 'Ưu đãi hiện có: ' . implode(' ', $parts) : 'Hiện chưa có chương trình ưu đãi nào đang diễn ra.';
    }

    private static function support(): array
    {
        return ['hotline' => Settings::get('hotline'), 'zalo' => Settings::get('zalo'), 'email' => Settings::get('support_email')];
    }

    private static function reply(string $text, string $source, string $question, array $extra = [], ?int $faqId = null, ?float $score = null): array
    {
        try {
            $q = preg_replace('/(\+?84|0)\d{9}/', '[sđt]', $question) ?? '';
            $q = preg_replace('/[\w.+-]+@[\w-]+\.[\w.]+/', '[email]', $q) ?? '';
            if (trim($q) !== '') {
                Db::insert('chat_questions', ['question' => mb_substr($q, 0, 500), 'source' => $source, 'matched_faq_id' => $faqId, 'score' => $score, 'created_at' => Clock::nowDb()]);
            }
        } catch (\Throwable) {
        }
        return ['reply' => $text, 'source' => $source] + $extra;
    }
}
