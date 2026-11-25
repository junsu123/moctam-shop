<?php
declare(strict_types=1);

namespace App\Http\Admin;

use App\Core\Auth;
use App\Core\Clock;
use App\Core\Db;

final class DashboardController extends Base
{
    private static ?array $counts = null;

    /** Số việc chờ trên menu, chỉ tính mục người dùng có quyền. */
    public static function navCounts(): array
    {
        if (self::$counts !== null) return self::$counts;
        $c = [];
        try {
            if (Auth::can('orders.view')) $c['orders'] = (int)Db::val("SELECT COUNT(*) FROM orders WHERE status = 'pending' OR needs_review = 1");
            if (Auth::can('payments.reconcile')) $c['discrepancies'] = (int)Db::val("SELECT COUNT(*) FROM payment_discrepancies WHERE status = 'open'");
            if (Auth::can('payments.view')) $c['refunds'] = (int)Db::val("SELECT COUNT(*) FROM refunds WHERE status = 'pending'");
            if (Auth::can('content.edit')) $c['faq_review'] = (int)Db::val("SELECT COUNT(*) FROM contents WHERE status = 'pending_review'");
            if (Auth::can('crosssell.review')) $c['crosssell'] = (int)Db::val("SELECT COUNT(*) FROM product_relations WHERE status = 'pending'");
            if (Auth::can('care.view')) $c['care'] = (int)Db::val("SELECT COUNT(*) FROM care_suggestions WHERE status = 'pending'");
            if (Auth::can('audit.view')) $c['monitor'] = count(array_filter(self::health(), fn($h) => $h['level'] !== 'ok'));
        } catch (\Throwable) {
        }
        return self::$counts = $c;
    }

    public function index(): string
    {
        $today = Clock::db(Clock::toLocal(Clock::nowDb())->setTime(0, 0)->setTimezone(new \DateTimeZone('UTC')));
        $data = [
            'title' => 'Tổng quan',
            'kpi' => [
                'orders_today' => (int)Db::val('SELECT COUNT(*) FROM orders WHERE created_at >= :t', ['t' => $today]),
                'revenue_today' => (int)Db::val("SELECT COALESCE(SUM(total),0) FROM orders WHERE created_at >= :t AND status <> 'cancelled'", ['t' => $today]),
                'pending' => (int)Db::val("SELECT COUNT(*) FROM orders WHERE status = 'pending'"),
                'qr_wait' => (int)Db::val("SELECT COUNT(*) FROM orders WHERE status = 'pending' AND payment_method = 'vietqr' AND payment_status IN ('unpaid','partial')"),
                'to_ship' => (int)Db::val("SELECT COUNT(*) FROM orders WHERE status = 'confirmed'"),
                'review' => (int)Db::val('SELECT COUNT(*) FROM orders WHERE needs_review = 1'),
            ],
            'low' => Db::all("SELECT s.id, s.sku_code, s.variant_label, p.name, i.on_hand, i.reserved, i.on_hand - i.reserved AS available FROM inventory i JOIN skus s ON s.id = i.sku_id JOIN products p ON p.id = s.product_id WHERE s.status = 'active' AND p.status = 'active' AND i.on_hand - i.reserved <= 10 ORDER BY available LIMIT 8"),
            'recent' => Auth::can('orders.view') ? Db::all('SELECT id, code, ship_name, total, status, payment_method, payment_status, created_at FROM orders ORDER BY id DESC LIMIT 8') : [],
            'health' => self::health(),
            'counts' => self::navCounts(),
        ];
        return $this->view('dashboard', $data);
    }

    /** Giám sát NFR-05: lỗi tạo đơn, giao dịch chờ đối soát, tác vụ hết hạn, tuổi sao lưu, độ trễ đồng bộ. */
    public static function health(): array
    {
        $now = Clock::now()->getTimestamp();
        $age = fn(?string $t) => $t ? (int)(($now - strtotime($t . ' UTC')) / 60) : null;
        $h = [];
        $err = (int)Db::val("SELECT COUNT(*) FROM error_logs WHERE channel = 'order' AND created_at >= :t", ['t' => Clock::db(Clock::now()->modify('-24 hours'))]);
        $h[] = ['name' => 'Lỗi tạo đơn (24 giờ)', 'value' => (string)$err, 'level' => $err === 0 ? 'ok' : ($err < 5 ? 'warn' : 'bad')];
        $rec = (int)Db::val("SELECT COUNT(*) FROM payment_discrepancies WHERE status = 'open'") + (int)Db::val("SELECT COUNT(*) FROM orders WHERE status = 'pending' AND payment_method = 'vietqr' AND payment_status <> 'unpaid'");
        $h[] = ['name' => 'Giao dịch chờ đối soát', 'value' => (string)$rec, 'level' => $rec === 0 ? 'ok' : 'warn'];
        $exp = Db::one("SELECT status, finished_at FROM job_runs WHERE job = 'expire_orders' ORDER BY id DESC LIMIT 1");
        $expFail = (int)Db::val("SELECT COUNT(*) FROM job_runs WHERE job = 'expire_orders' AND status = 'failed' AND started_at >= :t", ['t' => Clock::db(Clock::now()->modify('-24 hours'))]);
        $m = $age($exp['finished_at'] ?? null);
        $h[] = ['name' => 'Tác vụ hết hạn đơn', 'value' => $exp ? ($m . ' phút trước' . ($expFail ? ", $expFail lần lỗi/24h" : '')) : 'Chưa chạy — kiểm tra Cron', 'level' => !$exp || $m > 30 || $expFail ? 'bad' : 'ok'];
        $bk = Db::one("SELECT finished_at FROM job_runs WHERE job = 'backup' AND status = 'ok' ORDER BY id DESC LIMIT 1");
        $bm = $age($bk['finished_at'] ?? null);
        $h[] = ['name' => 'Tuổi bản sao lưu', 'value' => $bk ? round($bm / 60, 1) . ' giờ' : 'Chưa có bản sao lưu', 'level' => !$bk || $bm > 26 * 60 ? 'bad' : 'ok'];
        $miss = \App\Domain\LegalPages::missingSettings();
        $h[] = ['name' => 'Thông tin pháp lý trên website', 'value' => $miss ? 'Còn thiếu: ' . implode(', ', $miss) : 'Đã đủ', 'level' => $miss ? 'warn' : 'ok', 'note' => 'Điền trong Cấu hình → Thông tin pháp lý.'];
        $sync = Db::one("SELECT MAX(last_used_at) AS t FROM api_keys WHERE is_active = 1 AND scopes LIKE '%events:read%'");
        $sm = $age($sync['t'] ?? null);
        $h[] = ['name' => 'Độ trễ đồng bộ Python', 'value' => $sync['t'] ? $sm . ' phút từ lần đọc cuối' : 'Chưa kết nối', 'level' => !$sync['t'] ? 'warn' : ($sm > 24 * 60 ? 'warn' : 'ok'), 'note' => 'Máy cá nhân tắt không ảnh hưởng bán hàng.'];
        return $h;
    }

    public function monitor(): string
    {
        $this->need('audit.view');
        return $this->view('monitor', [
            'title' => 'Giám sát',
            'health' => self::health(),
            'jobs' => Db::all('SELECT * FROM job_runs ORDER BY id DESC LIMIT 30'),
            'errors' => Db::all('SELECT * FROM error_logs ORDER BY id DESC LIMIT 50'),
            'chat' => Db::all("SELECT source, COUNT(*) AS n FROM chat_questions WHERE created_at >= :t GROUP BY source", ['t' => Clock::db(Clock::now()->modify('-7 days'))]),
            'unanswered' => Db::all("SELECT question, COUNT(*) n FROM chat_questions WHERE source = 'fallback' AND created_at >= :t GROUP BY question ORDER BY n DESC LIMIT 15", ['t' => Clock::db(Clock::now()->modify('-30 days'))]),
        ]);
    }
}
