<?php
declare(strict_types=1);

namespace App\Http\Admin;

use App\Core\Db;
use App\Domain\PaymentService;

final class PaymentController extends Base
{
    public function index(): string
    {
        $this->need('payments.view');
        $page = max(1, $this->int('page', 1));
        $total = (int)Db::val('SELECT COUNT(*) FROM payment_receipts');
        return $this->view('payments', [
            'title' => 'Khoản thu',
            'rows' => Db::all('SELECT r.*, o.code, o.total, u.full_name FROM payment_receipts r LEFT JOIN orders o ON o.id = r.order_id LEFT JOIN users u ON u.id = r.recorded_by ORDER BY r.id DESC LIMIT 50 OFFSET :o', ['o' => ($page - 1) * 50]),
            'waiting' => Db::all("SELECT id, code, total, amount_received, expires_at, created_at, ship_name FROM orders WHERE payment_method = 'vietqr' AND status = 'pending' AND payment_status IN ('unpaid','partial') ORDER BY created_at LIMIT 50"),
            'page' => $page, 'pages' => (int)ceil($total / 50),
        ]);
    }

    public function recordVietQr(): void
    {
        $r = PaymentService::recordVietQr($_POST);
        $msg = 'Đã ghi nhận khoản thu' . ($r['order_code'] ? ' cho đơn ' . $r['order_code'] : ' (chưa khớp đơn)') . '.';
        if ($r['discrepancies']) {
            $msg .= ' Có sai lệch: ' . implode(', ', array_map(fn($d) => PaymentService::DISCREPANCY_LABELS[$d], $r['discrepancies'])) . ' — xem mục Sai lệch.';
        } elseif ($r['order_code']) {
            $msg .= ' Đủ tiền — nhân viên vận hành có thể xác nhận đơn.';
        }
        $this->back($msg);
    }

    public function discrepancies(): string
    {
        $this->need('payments.reconcile');
        $st = $this->str('status', 'open');
        return $this->view('discrepancies', [
            'title' => 'Sai lệch thanh toán', 'st' => $st,
            'rows' => Db::all('SELECT d.*, o.code, o.status AS order_status, o.total, o.amount_received, r.source, r.bank_txn_id, r.transfer_content, r.received_at, u.full_name
                                FROM payment_discrepancies d LEFT JOIN orders o ON o.id = d.order_id LEFT JOIN payment_receipts r ON r.id = d.receipt_id LEFT JOIN users u ON u.id = d.resolved_by
                                WHERE d.status = :s ORDER BY d.id DESC LIMIT 200', ['s' => $st === 'resolved' ? 'resolved' : 'open']),
        ]);
    }

    public function resolve(string $id): void
    {
        PaymentService::resolveDiscrepancy((int)$id, $_POST);
        $this->back('Đã xử lý sai lệch.');
    }

    public function refunds(): string
    {
        $this->need('payments.view');
        return $this->view('refunds', [
            'title' => 'Hoàn tiền',
            'rows' => Db::all("SELECT f.*, o.code, o.amount_received, o.amount_refunded, o.ship_name, u.full_name AS approver FROM refunds f JOIN orders o ON o.id = f.order_id LEFT JOIN users u ON u.id = f.approved_by ORDER BY FIELD(f.status,'pending','completed','cancelled'), f.id DESC LIMIT 200"),
        ]);
    }

    public function complete(string $id): void
    {
        PaymentService::completeRefund((int)$id, $_POST);
        $this->back('Đã ghi nhận hoàn tiền.');
    }

    public function cancel(string $id): void
    {
        PaymentService::cancelRefund((int)$id, $this->str('reason', 'Hủy yêu cầu hoàn'));
        $this->back('Đã hủy yêu cầu hoàn.');
    }
}
