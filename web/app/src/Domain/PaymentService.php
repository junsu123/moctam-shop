<?php
declare(strict_types=1);

namespace App\Domain;

use App\Core\ApiError;
use App\Core\Audit;
use App\Core\Auth;
use App\Core\Clock;
use App\Core\Db;

/**
 * Thanh toán, đối soát, hoàn tiền (FR-08, §4.3).
 * Trạng thái thanh toán = f(khoản đã thu, khoản đã hoàn), độc lập trạng thái giao hàng.
 */
final class PaymentService
{
    public const DISCREPANCY_LABELS = [
        'underpaid' => 'Chuyển thiếu', 'overpaid' => 'Chuyển thừa', 'wrong_content' => 'Sai nội dung',
        'late' => 'Chuyển sau hạn', 'after_cancel' => 'Tiền đến sau khi hủy', 'unmatched' => 'Chưa khớp đơn',
        'cod_mismatch' => 'COD lệch số tiền',
    ];

    public static function recalc(int $orderId): void
    {
        $o = Db::one('SELECT id, total FROM orders WHERE id = :id', ['id' => $orderId]);
        $received = (int)Db::val('SELECT COALESCE(SUM(amount),0) FROM payment_receipts WHERE order_id = :id', ['id' => $orderId]);
        $refunded = (int)Db::val("SELECT COALESCE(SUM(amount),0) FROM refunds WHERE order_id = :id AND status = 'completed'", ['id' => $orderId]);
        $total = (int)$o['total'];
        $status = match (true) {
            $refunded > 0 && $refunded >= $received => 'refunded',
            $refunded > 0 => 'partially_refunded',
            $received === 0 => 'unpaid',
            $received < $total => 'partial',
            $received === $total => 'paid',
            default => 'overpaid',
        };
        Db::update('orders', ['amount_received' => $received, 'amount_refunded' => $refunded, 'payment_status' => $status], 'id = :id', ['id' => $orderId]);
    }

    /** Khách mở trang xác nhận/quét QR: CHỈ ghi nhận bước hiển thị hướng dẫn. */
    public static function markQrViewed(int $orderId): void
    {
        Db::exec('UPDATE orders SET qr_viewed_at = COALESCE(qr_viewed_at, :t) WHERE id = :id', ['t' => Clock::nowDb(), 'id' => $orderId]);
    }

    /**
     * Nhân viên ghi nhận giao dịch VietQR đã thấy trên sao kê.
     * Không bao giờ tự chuyển đơn sang trạng thái sẵn sàng giao (AT-05).
     */
    public static function recordVietQr(array $in): array
    {
        Auth::require('payments.reconcile');
        $amount = (int)($in['amount'] ?? 0);
        $txn = trim((string)($in['bank_txn_id'] ?? ''));
        $source = trim((string)($in['source'] ?? '')) ?: 'VietQR';
        $receivedAt = Clock::fromLocalInput((string)($in['received_at'] ?? '')) ?? null;
        $content = trim((string)($in['transfer_content'] ?? ''));
        $orderCode = strtoupper(trim((string)($in['order_code'] ?? '')));
        $errors = [];
        if ($amount <= 0) $errors['amount'] = 'Số tiền phải lớn hơn 0';
        if ($txn === '') $errors['bank_txn_id'] = 'Bắt buộc mã giao dịch ngân hàng';
        if (!$receivedAt) $errors['received_at'] = 'Bắt buộc thời điểm nhận';
        if ($errors) throw ApiError::validation($errors);

        return Db::tx(function () use ($amount, $txn, $source, $receivedAt, $content, $orderCode, $in) {
            $order = null;
            if ($orderCode === '' && $content !== '') {
                // Thử khớp đơn từ nội dung chuyển khoản
                if (preg_match('/\b([A-Z]{1,4}\d{6}[A-Z0-9]{4})\b/', strtoupper($content), $m)) {
                    $orderCode = $m[1];
                }
            }
            if ($orderCode !== '') {
                $order = Db::one('SELECT * FROM orders WHERE code = :c FOR UPDATE', ['c' => $orderCode]);
                if (!$order && !empty($in['order_code'])) {
                    throw ApiError::validation(['order_code' => 'Không tìm thấy đơn ' . $orderCode]);
                }
            }
            try {
                $rid = Db::insert('payment_receipts', [
                    'order_id' => $order['id'] ?? null, 'method' => 'vietqr', 'source' => $source, 'bank_txn_id' => $txn,
                    'amount' => $amount, 'transfer_content' => $content ?: null, 'received_at' => $receivedAt,
                    'recorded_by' => Auth::id(), 'note' => trim((string)($in['note'] ?? '')) ?: null, 'created_at' => Clock::nowDb(),
                ]);
            } catch (\PDOException $e) {
                if (Db::isDuplicate($e)) {
                    throw new ApiError('DUPLICATE_TXN', "Mã giao dịch $txn của nguồn $source đã được ghi nhận trước đó.", 409);
                }
                throw $e;
            }

            $flags = [];
            if (!$order) {
                $flags[] = ['unmatched', null];
            } else {
                $prev = (int)$order['amount_received'];
                $total = (int)$order['total'];
                if (in_array($order['status'], ['cancelled'], true)) {
                    $flags[] = ['after_cancel', $total];
                } else {
                    if ($prev + $amount < $total) $flags[] = ['underpaid', $total];
                    if ($prev + $amount > $total) $flags[] = ['overpaid', $total];
                    if ($receivedAt > $order['expires_at']) $flags[] = ['late', $total];
                }
                if ($content !== '' && !str_contains(strtoupper(preg_replace('/\s+/', '', $content)), $order['transfer_content'])) {
                    $flags[] = ['wrong_content', null];
                }
            }
            foreach ($flags as [$type, $expected]) {
                Db::insert('payment_discrepancies', [
                    'order_id' => $order['id'] ?? null, 'receipt_id' => $rid, 'type' => $type,
                    'expected_amount' => $expected, 'actual_amount' => $amount, 'status' => 'open', 'created_at' => Clock::nowDb(),
                ]);
            }
            Audit::log('payment.receipt', 'payment_receipt', (string)$rid, null, ['order' => $order['code'] ?? null, 'amount' => $amount, 'source' => $source, 'txn' => $txn, 'flags' => array_column($flags, 0)]);
            if ($order) {
                self::recalc((int)$order['id']);
                SyncService::emitOrder((int)$order['id'], 'order.payment_changed');
            }
            return ['receipt_id' => $rid, 'order_code' => $order['code'] ?? null, 'discrepancies' => array_column($flags, 0)];
        });
    }

    /** COD: ghi nhận đã thu sau khi đối soát khoản tiền từ người giao/hãng vận chuyển. */
    public static function recordCod(int $orderId, array $in): array
    {
        Auth::require('payments.reconcile');
        $amount = (int)($in['amount'] ?? 0);
        $ref = trim((string)($in['bank_txn_id'] ?? ''));
        $source = trim((string)($in['source'] ?? '')) ?: 'COD';
        $receivedAt = Clock::fromLocalInput((string)($in['received_at'] ?? '')) ?? Clock::nowDb();
        if ($amount <= 0 || $ref === '') {
            throw ApiError::validation(['amount' => $amount <= 0 ? 'Số tiền phải lớn hơn 0' : null, 'bank_txn_id' => $ref === '' ? 'Bắt buộc mã bảng kê/đối soát' : null]);
        }
        return Db::tx(function () use ($orderId, $amount, $ref, $source, $receivedAt, $in) {
            $o = Db::one('SELECT * FROM orders WHERE id = :id FOR UPDATE', ['id' => $orderId]);
            if (!$o || $o['payment_method'] !== 'cod') throw ApiError::notFound('Không tìm thấy đơn COD.');
            if (!in_array($o['status'], ['delivered', 'returning', 'returned'], true)) {
                throw new ApiError('COD_NOT_DELIVERED', 'Chỉ đối soát COD sau khi đơn được ghi nhận giao thành công.', 409);
            }
            try {
                $rid = Db::insert('payment_receipts', [
                    'order_id' => $orderId, 'method' => 'cod', 'source' => $source, 'bank_txn_id' => $ref, 'amount' => $amount,
                    'received_at' => $receivedAt, 'recorded_by' => Auth::id(), 'note' => trim((string)($in['note'] ?? '')) ?: null, 'created_at' => Clock::nowDb(),
                ]);
            } catch (\PDOException $e) {
                if (Db::isDuplicate($e)) throw new ApiError('DUPLICATE_TXN', 'Mã đối soát này đã được ghi nhận.', 409);
                throw $e;
            }
            $expected = (int)$o['total'] - (int)$o['amount_received'];
            $disc = [];
            if ($amount !== $expected) {
                Db::insert('payment_discrepancies', [
                    'order_id' => $orderId, 'receipt_id' => $rid, 'type' => 'cod_mismatch', 'expected_amount' => $expected,
                    'actual_amount' => $amount, 'status' => 'open', 'created_at' => Clock::nowDb(),
                ]);
                $disc[] = 'cod_mismatch';
            }
            Audit::log('payment.cod', 'order', (string)$orderId, null, ['amount' => $amount, 'ref' => $ref, 'source' => $source]);
            self::recalc($orderId);
            SyncService::emitOrder($orderId, 'order.payment_changed');
            return ['receipt_id' => $rid, 'discrepancies' => $disc];
        });
    }

    /** Xử lý sai lệch. resolution: accepted | customer_topup | refund | replacement_order | other; có thể gắn đơn cho khoản chưa khớp. */
    public static function resolveDiscrepancy(int $id, array $in): void
    {
        Auth::require('payments.reconcile');
        $resolution = (string)($in['resolution'] ?? '');
        $note = trim((string)($in['resolution_note'] ?? ''));
        if (!in_array($resolution, ['accepted', 'customer_topup', 'refund', 'replacement_order', 'other'], true) || $note === '') {
            throw ApiError::validation(['resolution' => 'Chọn hướng xử lý', 'resolution_note' => $note === '' ? 'Ghi rõ nội dung đã thống nhất với khách' : null]);
        }
        Db::tx(function () use ($id, $resolution, $note, $in) {
            $d = Db::one('SELECT * FROM payment_discrepancies WHERE id = :id FOR UPDATE', ['id' => $id]);
            if (!$d || $d['status'] !== 'open') throw ApiError::notFound('Sai lệch không tồn tại hoặc đã xử lý.');
            $orderId = $d['order_id'] ? (int)$d['order_id'] : null;

            // Gắn khoản chưa khớp vào một đơn
            $link = strtoupper(trim((string)($in['link_order_code'] ?? '')));
            if ($d['type'] === 'unmatched' && $link !== '') {
                $o = Db::one('SELECT id FROM orders WHERE code = :c FOR UPDATE', ['c' => $link]);
                if (!$o) throw ApiError::validation(['link_order_code' => 'Không tìm thấy đơn ' . $link]);
                $orderId = (int)$o['id'];
                Db::update('payment_receipts', ['order_id' => $orderId], 'id = :id', ['id' => $d['receipt_id']]);
                Db::update('payment_discrepancies', ['order_id' => $orderId], 'id = :id', ['id' => $id]);
            }
            if ($resolution === 'refund') {
                if (!$orderId) throw ApiError::validation(['link_order_code' => 'Cần gắn đơn trước khi tạo hoàn tiền']);
                $amount = (int)($in['refund_amount'] ?? 0);
                self::createRefund($orderId, $amount, 'Xử lý sai lệch #' . $id . ': ' . $note, true);
            }
            Db::update('payment_discrepancies', [
                'status' => 'resolved', 'resolution' => $resolution, 'resolution_note' => mb_substr($note, 0, 500),
                'resolved_by' => Auth::id(), 'resolved_at' => Clock::nowDb(),
            ], 'id = :id', ['id' => $id]);
            Audit::log('payment.discrepancy_resolved', 'discrepancy', (string)$id, ['status' => 'open', 'type' => $d['type']], ['resolution' => $resolution], $note);
            if ($orderId) {
                self::recalc($orderId);
                SyncService::emitOrder($orderId, 'order.payment_changed');
            }
        });
    }

    /** Tạo yêu cầu hoàn (chờ chuyển). Tổng hoàn ≤ tổng thực nhận. */
    public static function createRefund(int $orderId, int $amount, string $reason, bool $fromReconcile = false): int
    {
        Auth::require($fromReconcile ? 'payments.reconcile' : 'refunds.approve');
        $reason = trim($reason);
        if ($amount <= 0 || $reason === '') {
            throw ApiError::validation(['refund_amount' => $amount <= 0 ? 'Số tiền hoàn phải > 0' : null, 'reason' => $reason === '' ? 'Bắt buộc lý do' : null]);
        }
        return Db::tx(function () use ($orderId, $amount, $reason) {
            $o = Db::one('SELECT * FROM orders WHERE id = :id FOR UPDATE', ['id' => $orderId]);
            if (!$o) throw ApiError::notFound();
            $committed = (int)$o['amount_refunded'] + (int)Db::val("SELECT COALESCE(SUM(amount),0) FROM refunds WHERE order_id = :id AND status = 'pending'", ['id' => $orderId]);
            if ($committed + $amount > (int)$o['amount_received']) {
                throw new ApiError('REFUND_EXCEEDS_RECEIVED', 'Tổng tiền hoàn vượt tổng tiền thực nhận (' . money($o['amount_received']) . ').', 422);
            }
            $id = Db::insert('refunds', [
                'order_id' => $orderId, 'amount' => $amount, 'reason' => mb_substr($reason, 0, 500), 'status' => 'pending',
                'requested_by' => Auth::id(), 'created_at' => Clock::nowDb(), 'updated_at' => Clock::nowDb(),
            ]);
            Audit::log('refund.created', 'refund', (string)$id, null, ['order_id' => $orderId, 'amount' => $amount], $reason);
            return $id;
        });
    }

    /** Duyệt & ghi nhận đã chuyển hoàn: lưu người duyệt, giao dịch hoàn, thời điểm (AT-07: cần refunds.approve). */
    public static function completeRefund(int $refundId, array $in): void
    {
        Auth::require('refunds.approve');
        $ref = trim((string)($in['refund_txn_ref'] ?? ''));
        $at = Clock::fromLocalInput((string)($in['refunded_at'] ?? '')) ?? Clock::nowDb();
        if ($ref === '') throw ApiError::validation(['refund_txn_ref' => 'Bắt buộc mã giao dịch hoàn']);
        Db::tx(function () use ($refundId, $ref, $at) {
            $r = Db::one('SELECT * FROM refunds WHERE id = :id FOR UPDATE', ['id' => $refundId]);
            if (!$r || $r['status'] !== 'pending') throw ApiError::notFound('Yêu cầu hoàn không tồn tại hoặc đã xử lý.');
            $o = Db::one('SELECT * FROM orders WHERE id = :id FOR UPDATE', ['id' => $r['order_id']]);
            if ((int)$o['amount_refunded'] + (int)$r['amount'] > (int)$o['amount_received']) {
                throw new ApiError('REFUND_EXCEEDS_RECEIVED', 'Tổng tiền hoàn vượt tổng tiền thực nhận.', 422);
            }
            Db::update('refunds', ['status' => 'completed', 'approved_by' => Auth::id(), 'refund_txn_ref' => mb_substr($ref, 0, 80), 'refunded_at' => $at, 'updated_at' => Clock::nowDb()], 'id = :id', ['id' => $refundId]);
            Audit::log('refund.completed', 'refund', (string)$refundId, ['status' => 'pending'], ['status' => 'completed', 'amount' => (int)$r['amount'], 'txn' => $ref]);
            self::recalc((int)$r['order_id']);
            SyncService::emitOrder((int)$r['order_id'], 'order.payment_changed');
        });
    }

    public static function cancelRefund(int $refundId, string $reason): void
    {
        Auth::require('refunds.approve');
        Db::tx(function () use ($refundId, $reason) {
            $r = Db::one('SELECT * FROM refunds WHERE id = :id FOR UPDATE', ['id' => $refundId]);
            if (!$r || $r['status'] !== 'pending') throw ApiError::notFound();
            Db::update('refunds', ['status' => 'cancelled', 'approved_by' => Auth::id(), 'updated_at' => Clock::nowDb()], 'id = :id', ['id' => $refundId]);
            Audit::log('refund.cancelled', 'refund', (string)$refundId, null, null, $reason);
        });
    }
}
