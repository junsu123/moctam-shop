<?php
declare(strict_types=1);

namespace App\Http\Admin;

use App\Core\ApiError;
use App\Core\Audit;
use App\Core\Auth;
use App\Core\Clock;
use App\Core\Db;

/**
 * Danh sách chăm sóc lại (FR-11): Python đề xuất, nhân viên xem xét.
 * Chỉ khách ĐÃ ĐỒNG Ý mới được dùng cho tiếp thị — xuất CSV và nút "Đã liên hệ" bị khóa với khách chưa đồng ý.
 */
final class CareController extends Base
{
    public function index(): string
    {
        $this->need('care.view');
        $st = in_array($s = $this->str('status', 'pending'), ['pending', 'contacted', 'skipped'], true) ? $s : 'pending';
        $consentOnly = $this->str('consent', '1') === '1';
        $rows = Db::all('SELECT cs.*, c.full_name, c.phone, c.marketing_consent, cat.name AS cat_name,
                                (SELECT COUNT(*) FROM orders o WHERE o.customer_id = c.id AND o.status = \'delivered\') AS delivered_orders
                           FROM care_suggestions cs JOIN customers c ON c.id = cs.customer_id LEFT JOIN categories cat ON cat.id = cs.category_id
                          WHERE cs.status = :s' . ($consentOnly ? ' AND c.marketing_consent = 1' : '') . ' ORDER BY cs.due_date, cs.score DESC LIMIT 300', ['s' => $st]);
        $hidden = $consentOnly ? (int)Db::val('SELECT COUNT(*) FROM care_suggestions cs JOIN customers c ON c.id = cs.customer_id WHERE cs.status = :s AND c.marketing_consent = 0', ['s' => $st]) : 0;
        Audit::log('care.view', 'care_list', $st, null, ['rows' => count($rows)]);
        return $this->view('care', ['title' => 'Chăm sóc lại', 'rows' => $rows, 'st' => $st, 'consentOnly' => $consentOnly, 'hidden' => $hidden]);
    }

    public function status(string $id): never
    {
        $this->need('care.view');
        $to = $this->str('to');
        if (!in_array($to, ['contacted', 'skipped', 'pending'], true)) throw ApiError::validation(['to' => 'Không hợp lệ']);
        $row = Db::one('SELECT cs.*, c.marketing_consent FROM care_suggestions cs JOIN customers c ON c.id = cs.customer_id WHERE cs.id = :id', ['id' => (int)$id]);
        if (!$row) throw ApiError::notFound();
        if ($to === 'contacted' && !$row['marketing_consent']) {
            throw new ApiError('NO_CONSENT', 'Khách chưa đồng ý nhận tiếp thị — không dùng danh sách này để liên hệ chào hàng.', 409);
        }
        Db::update('care_suggestions', ['status' => $to, 'handled_by' => Auth::id(), 'handled_at' => Clock::nowDb()], 'id = :id', ['id' => (int)$id]);
        Audit::log('care.status', 'care_suggestion', $id, ['status' => $row['status']], ['status' => $to]);
        $this->back('Đã cập nhật.');
    }

    /** Xuất CSV — chỉ khách đã đồng ý. */
    public function export(): never
    {
        $this->need('care.view');
        $rows = Db::all("SELECT c.full_name, c.phone, cat.name AS cat_name, cs.last_order_at, cs.due_date, cs.reason FROM care_suggestions cs JOIN customers c ON c.id = cs.customer_id LEFT JOIN categories cat ON cat.id = cs.category_id
                         WHERE cs.status = 'pending' AND c.marketing_consent = 1 ORDER BY cs.due_date");
        Audit::log('care.export', 'care_list', 'pending', null, ['rows' => count($rows)], 'Xuất danh sách khách đã đồng ý');
        header('Content-Type: text/csv; charset=utf-8');
        header('Content-Disposition: attachment; filename="cham-soc-lai-' . Clock::now()->format('Ymd') . '.csv"');
        $out = fopen('php://output', 'w');
        fwrite($out, "\xEF\xBB\xBF");
        fputcsv($out, ['Họ tên', 'Số điện thoại', 'Nhóm hàng', 'Lần mua cuối', 'Đến kỳ', 'Lý do']);
        foreach ($rows as $r) {
            fputcsv($out, [$r['full_name'], $r['phone'], $r['cat_name'], $r['last_order_at'] ? vn_time($r['last_order_at'], 'd/m/Y') : '', $r['due_date'], $r['reason']]);
        }
        exit;
    }
}
