<?php
declare(strict_types=1);

namespace App\Http\Admin;

use App\Core\ApiError;
use App\Core\Auth;
use App\Core\Clock;
use App\Core\Db;
use App\Core\Text;
use App\Domain\OrderService;
use App\Domain\PaymentService;

final class OrderController extends Base
{
    public function index(): string
    {
        $this->need('orders.view');
        $where = ['1=1'];
        $p = [];
        $status = $this->str('status');
        if ($status === 'review') {
            $where[] = 'o.needs_review = 1';
        } elseif (isset(OrderService::STATUS_LABELS[$status])) {
            $where[] = 'o.status = :st';
            $p['st'] = $status;
        }
        if (in_array($m = $this->str('method'), ['cod', 'vietqr'], true)) {
            $where[] = 'o.payment_method = :m';
            $p['m'] = $m;
        }
        if (isset(OrderService::PAYMENT_LABELS[$ps = $this->str('pay')])) {
            $where[] = 'o.payment_status = :ps';
            $p['ps'] = $ps;
        }
        if (($q = $this->str('q')) !== '') {
            $phone = Text::normalizePhone($q);
            $where[] = '(o.code LIKE :q OR o.ship_phone = :ph OR o.tracking_code = :tc)';
            $p += ['q' => '%' . strtoupper($q) . '%', 'ph' => $phone ?? $q, 'tc' => $q];
        }
        if ($from = Clock::fromLocalInput($this->str('from') ? $this->str('from') . 'T00:00' : '')) { $where[] = 'o.created_at >= :f'; $p['f'] = $from; }
        if ($to = Clock::fromLocalInput($this->str('to') ? $this->str('to') . 'T23:59' : '')) { $where[] = 'o.created_at <= :t'; $p['t'] = $to; }
        $w = implode(' AND ', $where);
        $total = (int)Db::val("SELECT COUNT(*) FROM orders o WHERE $w", $p);
        $page = max(1, $this->int('page', 1));
        $per = 30;
        $rows = Db::all("SELECT o.id, o.code, o.ship_name, o.ship_phone, o.ship_province, o.total, o.status, o.payment_method, o.payment_status, o.needs_review, o.expires_at, o.created_at, o.tracking_code,
                         (SELECT COUNT(*) FROM payment_discrepancies d WHERE d.order_id = o.id AND d.status = 'open') AS open_disc
                         FROM orders o WHERE $w ORDER BY o.id DESC LIMIT :l OFFSET :o", $p + ['l' => $per, 'o' => ($page - 1) * $per]);
        $statusCounts = [];
        foreach (Db::all('SELECT status, COUNT(*) n FROM orders GROUP BY status') as $r) $statusCounts[$r['status']] = (int)$r['n'];
        $statusCounts['review'] = (int)Db::val('SELECT COUNT(*) FROM orders WHERE needs_review = 1');
        return $this->view('orders', ['title' => 'Đơn hàng', 'rows' => $rows, 'total' => $total, 'page' => $page, 'pages' => (int)ceil($total / $per), 'f' => $_GET, 'statusCounts' => $statusCounts]);
    }

    public function show(string $id): string
    {
        $this->need('orders.view');
        $o = Db::one('SELECT o.*, c.marketing_consent, c.customer_key FROM orders o JOIN customers c ON c.id = o.customer_id WHERE o.id = :id', ['id' => (int)$id]);
        if (!$o) throw ApiError::notFound('Không tìm thấy đơn.');
        $canPay = Auth::can('payments.view');
        return $this->view('order_show', [
            'title' => 'Đơn ' . $o['code'],
            'o' => $o,
            'items' => Db::all('SELECT * FROM order_items WHERE order_id = :id ORDER BY id', ['id' => $o['id']]),
            'history' => Db::all('SELECT h.*, u.full_name FROM order_status_history h LEFT JOIN users u ON u.id = h.user_id WHERE h.order_id = :id ORDER BY h.id', ['id' => $o['id']]),
            'receipts' => $canPay ? Db::all('SELECT r.*, u.full_name FROM payment_receipts r LEFT JOIN users u ON u.id = r.recorded_by WHERE r.order_id = :id ORDER BY r.id', ['id' => $o['id']]) : [],
            'discs' => $canPay ? Db::all('SELECT * FROM payment_discrepancies WHERE order_id = :id ORDER BY id', ['id' => $o['id']]) : [],
            'refunds' => $canPay ? Db::all('SELECT r.*, u.full_name AS approver FROM refunds r LEFT JOIN users u ON u.id = r.approved_by WHERE r.order_id = :id ORDER BY r.id', ['id' => $o['id']]) : [],
            'movements' => Db::all('SELECT m.*, s.sku_code FROM inventory_movements m JOIN skus s ON s.id = m.sku_id WHERE m.order_id = :id ORDER BY m.id', ['id' => $o['id']]),
            'voucher' => Db::one('SELECT * FROM voucher_usages WHERE order_id = :id', ['id' => $o['id']]),
            'canPay' => $canPay,
        ]);
    }

    public function transition(string $id): never
    {
        $to = $this->str('to');
        $extra = [
            'carrier_name' => $this->str('carrier_name'),
            'tracking_code' => $this->str('tracking_code'),
            'inspection' => is_array($_POST['inspection'] ?? null) ? $_POST['inspection'] : [],
        ];
        OrderService::transition((int)$id, $to, $this->str('reason') ?: null, $extra);
        $this->back('Đã chuyển đơn sang "' . (OrderService::STATUS_LABELS[$to] ?? $to) . '".');
    }

    public function tracking(string $id): never
    {
        OrderService::updateShipping((int)$id, $_POST);
        $this->back('Đã lưu thông tin vận đơn.');
    }

    public function cod(string $id): never
    {
        $r = PaymentService::recordCod((int)$id, $_POST);
        $this->back($r['discrepancies'] ? 'Đã ghi nhận khoản COD — số tiền lệch, đã đưa vào danh sách sai lệch.' : 'Đã ghi nhận đã thu COD.');
    }

    public function refund(string $id): never
    {
        PaymentService::createRefund((int)$id, $this->int('refund_amount'), $this->str('reason'));
        $this->back('Đã tạo yêu cầu hoàn tiền, chờ ghi nhận giao dịch hoàn.');
    }
}
