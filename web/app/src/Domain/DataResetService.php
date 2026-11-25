<?php
declare(strict_types=1);

namespace App\Domain;

use App\Core\ApiError;
use App\Core\Audit;
use App\Core\Clock;
use App\Core\Db;
use App\Core\Settings;
use App\Core\Ulid;

/**
 * Làm mới dữ liệu trước khi chạy thật: xóa dữ liệu thử, GIỮ cấu hình, vai trò, danh mục,
 * vùng giao, trang chính sách và tài khoản quản trị.
 *
 * Luôn xóa (dữ liệu giao dịch thử): đơn, khách, tài khoản khách (Google/Facebook), khoản thu, sai lệch, hoàn tiền, lượt voucher,
 *   khóa gửi lại, danh sách chăm sóc, gợi ý mua kèm do AI, nội dung AI chưa xuất bản, sự kiện đồng bộ,
 *   biến động kho; tồn đang giữ về 0; lượt dùng voucher về 0.
 * Tùy chọn:
 *   products   — xóa sản phẩm, SKU, tồn, ảnh, gợi ý mua kèm (dữ liệu mẫu)
 *   promotions — xóa voucher và Flash Sale
 *   content    — xóa blog và FAQ (giữ trang chính sách)
 *   demo_users — xóa tài khoản mẫu @xuong.local
 *   stock_zero — đặt tồn thực tế về 0 (khi giữ sản phẩm, để nhập tồn đầu kỳ thật)
 *   logs       — xóa nhật ký thao tác, lỗi, tác vụ, câu hỏi chat, giới hạn tần suất của giai đoạn thử
 *   api_keys   — thu hồi mọi khóa API Python
 *
 * Đồng bộ Python: ghi sự kiện "system.data_reset" và đánh dấu mọi con trỏ cũ hết hiệu lực →
 * dịch vụ Python nhận 410 CURSOR_EXPIRED và tự tải lại bản chụp (rỗng) ở lần đồng bộ kế tiếp.
 */
final class DataResetService
{
    public const CONFIRM_PHRASE = 'XOA DU LIEU THU';

    public const OPTIONS = [
        'products'   => 'Xóa sản phẩm, quy cách (SKU), tồn kho, ảnh và gợi ý mua kèm',
        'promotions' => 'Xóa voucher và Flash Sale',
        'content'    => 'Xóa bài blog và FAQ (giữ trang chính sách)',
        'demo_users' => 'Xóa tài khoản mẫu @xuong.local',
        'stock_zero' => 'Đặt tồn thực tế về 0 (khi giữ sản phẩm, để nhập tồn đầu kỳ thật)',
        'logs'       => 'Xóa nhật ký thao tác, nhật ký lỗi, lịch sử tác vụ, câu hỏi chat của giai đoạn thử',
        'api_keys'   => 'Thu hồi mọi khóa API của dịch vụ Python',
    ];

    public static function normalize(array $in): array
    {
        $o = [];
        foreach (array_keys(self::OPTIONS) as $k) {
            $o[$k] = !empty($in[$k]);
        }
        if ($o['products']) $o['stock_zero'] = false; // không còn sản phẩm để đặt tồn
        return $o;
    }

    /** Đếm số bản ghi sẽ bị ảnh hưởng — hiển thị trước khi xác nhận. */
    public static function preview(array $opts): array
    {
        $o = self::normalize($opts);
        $c = fn(string $sql) => (int)Db::val($sql);
        $p = [
            'Đơn hàng' => $c('SELECT COUNT(*) FROM orders'),
            'Khách hàng' => $c('SELECT COUNT(*) FROM customers'),
            'Tài khoản khách (Google/Facebook)' => $c('SELECT COUNT(*) FROM customer_accounts'),
            'Khoản thu' => $c('SELECT COUNT(*) FROM payment_receipts'),
            'Sai lệch thanh toán' => $c('SELECT COUNT(*) FROM payment_discrepancies'),
            'Yêu cầu hoàn tiền' => $c('SELECT COUNT(*) FROM refunds'),
            'Danh sách chăm sóc lại' => $c('SELECT COUNT(*) FROM care_suggestions'),
            'Biến động kho' => $c('SELECT COUNT(*) FROM inventory_movements'),
            'Sự kiện đồng bộ' => $c('SELECT COUNT(*) FROM sync_events'),
            'Gợi ý mua kèm do AI' => $c("SELECT COUNT(*) FROM product_relations WHERE source = 'ai'"),
            'Nội dung AI chưa xuất bản' => $c("SELECT COUNT(*) FROM contents WHERE source = 'ai' AND published_version_id IS NULL"),
        ];
        if ($o['products']) {
            $p['Sản phẩm'] = $c('SELECT COUNT(*) FROM products');
            $p['Quy cách (SKU)'] = $c('SELECT COUNT(*) FROM skus');
            $p['Ảnh sản phẩm'] = $c('SELECT COUNT(*) FROM product_images');
        }
        if ($o['promotions']) {
            $p['Voucher'] = $c('SELECT COUNT(*) FROM vouchers');
            $p['Flash Sale'] = $c('SELECT COUNT(*) FROM flash_sales');
        }
        if ($o['content']) {
            $p['Bài blog'] = $c("SELECT COUNT(*) FROM contents WHERE kind = 'blog'");
            $p['FAQ'] = $c("SELECT COUNT(*) FROM contents WHERE kind = 'faq'");
        }
        if ($o['demo_users']) $p['Tài khoản mẫu'] = $c("SELECT COUNT(*) FROM users WHERE email LIKE '%@xuong.local'");
        if ($o['stock_zero']) $p['SKU đặt tồn về 0'] = $c('SELECT COUNT(*) FROM inventory WHERE on_hand <> 0');
        if ($o['logs']) $p['Dòng nhật ký'] = $c('SELECT COUNT(*) FROM audit_logs') + $c('SELECT COUNT(*) FROM error_logs') + $c('SELECT COUNT(*) FROM job_runs') + $c('SELECT COUNT(*) FROM chat_questions');
        if ($o['api_keys']) $p['Khóa API đang dùng'] = $c('SELECT COUNT(*) FROM api_keys WHERE is_active = 1');
        return $p;
    }

    /**
     * Thực hiện. $actorUserId: người thao tác (không bị xóa kể cả khi là tài khoản mẫu).
     * @return array{deleted: array<string,int>, backup: ?array}
     */
    public static function run(array $opts, ?int $actorUserId, bool $backup = true): array
    {
        $o = self::normalize($opts);
        $before = self::preview($o);

        // 1) Sao lưu trước — lỗi sao lưu thì DỪNG, không xóa gì
        $bk = null;
        if ($backup) {
            try {
                $bk = BackupService::run('truoc-lam-moi', 30);
            } catch (\Throwable $e) {
                throw new ApiError('BACKUP_FAILED', 'Không sao lưu được nên chưa xóa dữ liệu: ' . $e->getMessage(), 500);
            }
        }

        $imagesToDelete = [];
        Db::tx(function () use ($o, $actorUserId, &$imagesToDelete) {
            $x = fn(string $sql, array $p = []) => Db::exec($sql, $p);

            // 2) Dữ liệu giao dịch thử (thứ tự theo khóa ngoại)
            $x('DELETE FROM idempotency_keys');
            $x('DELETE FROM voucher_usages');
            $x('DELETE FROM payment_discrepancies');
            $x('DELETE FROM refunds');
            $x('DELETE FROM payment_receipts');
            $x('DELETE FROM order_status_history');
            $x('DELETE FROM order_items');
            $x('DELETE FROM care_suggestions');
            $x('DELETE FROM orders');
            $x('DELETE FROM customers');
            $x('DELETE FROM customer_accounts'); // danh tính đăng nhập xóa theo ON DELETE CASCADE
            $x('DELETE FROM account_deletions');
            $x('DELETE FROM inventory_movements');
            $x('UPDATE inventory SET reserved = 0, updated_at = :t', ['t' => Clock::nowDb()]);
            $x('UPDATE vouchers SET reserved_count = 0, used_count = 0');
            $x("DELETE FROM product_relations WHERE source = 'ai'");
            $x("DELETE FROM contents WHERE source = 'ai' AND published_version_id IS NULL");
            $x('DELETE FROM sync_inbox');

            // 3) Tùy chọn
            if ($o['promotions']) {
                $x('DELETE FROM flash_sale_items');
                $x('DELETE FROM flash_sales');
                $x('DELETE FROM vouchers');
            }
            if ($o['products']) {
                foreach (Db::all("SELECT path FROM product_images WHERE path LIKE '/uploads/%'") as $r) $imagesToDelete[] = $r['path'];
                $x('DELETE FROM flash_sale_items');
                $x('DELETE FROM product_relations');
                $x('DELETE FROM product_images');
                $x('DELETE FROM inventory');
                $x('UPDATE contents SET product_id = NULL WHERE product_id IS NOT NULL');
                $x('DELETE FROM skus');
                $x('DELETE FROM products');
            } elseif ($o['stock_zero']) {
                $x('UPDATE inventory SET on_hand = 0, updated_at = :t', ['t' => Clock::nowDb()]);
            }
            if (!$o['products']) {
                // Mốc tồn đầu kỳ sau khi làm mới, để lịch sử kho bắt đầu sạch
                foreach (Db::all('SELECT sku_id, on_hand FROM inventory') as $i) {
                    Db::insert('inventory_movements', [
                        'sku_id' => $i['sku_id'], 'type' => 'adjust', 'on_hand_delta' => 0, 'reserved_delta' => 0,
                        'on_hand_after' => (int)$i['on_hand'], 'reserved_after' => 0, 'reason' => 'Tồn đầu kỳ sau làm mới dữ liệu',
                        'user_id' => $actorUserId, 'created_at' => Clock::nowDb(),
                    ]);
                }
            }
            if ($o['content']) {
                $x("DELETE FROM contents WHERE kind IN ('blog','faq')"); // content_versions xóa theo ON DELETE CASCADE
            }
            if ($o['demo_users']) {
                $x("DELETE FROM users WHERE email LIKE '%@xuong.local' AND id <> :me", ['me' => $actorUserId ?? 0]);
            }
            if ($o['api_keys']) {
                $x('UPDATE api_keys SET is_active = 0');
            }
            if ($o['logs']) {
                $x('DELETE FROM audit_logs');
                $x('DELETE FROM error_logs');
                $x('DELETE FROM job_runs WHERE job <> \'backup\'');
                $x('DELETE FROM chat_questions');
                $x('DELETE FROM rate_limits');
            }

            // 4) Đồng bộ: mốc mới, mọi con trỏ cũ hết hiệu lực → Python tải lại bản chụp
            $seq = SyncService::emit('system', 0, 'system.data_reset', ['at' => Clock::nowDb()]);
            $x('DELETE FROM sync_events WHERE seq < :s', ['s' => $seq]);
            Settings::set('sync_pruned_through', (string)$seq);
            Settings::set('data_reset_at', Clock::nowDb());
        });

        foreach ($imagesToDelete as $path) {
            @unlink(rtrim((string)config('paths.uploads'), '/') . substr($path, strlen('/uploads')));
        }
        $deleted = array_filter($before);
        Audit::log('data.reset', 'system', 'database', null, ['options' => array_keys(array_filter($o)), 'deleted' => $deleted, 'backup' => $bk ? basename($bk['file']) : null],
            'Làm mới dữ liệu trước khi chạy thật', $actorUserId ? 'user' : 'system');
        return ['deleted' => $deleted, 'backup' => $bk];
    }
}
