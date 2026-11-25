<?php
declare(strict_types=1);

namespace App\Domain;

use App\Core\ApiError;
use App\Core\Audit;
use App\Core\Auth;
use App\Core\Clock;
use App\Core\Db;

/**
 * Tồn khả dụng = on_hand − reserved. Mọi thay đổi dùng UPDATE có điều kiện
 * trong giao dịch → hai đơn đồng thời không thể vượt quá hàng còn (AT-01).
 */
final class InventoryService
{
    /** Giữ tồn; trả false nếu không đủ. */
    public static function reserve(int $skuId, int $qty, int $orderId, string $transitionKey): bool
    {
        $n = Db::exec(
            'UPDATE inventory SET reserved = reserved + :q, updated_at = :t WHERE sku_id = :s AND on_hand - reserved >= :q2',
            ['q' => $qty, 'q2' => $qty, 's' => $skuId, 't' => Clock::nowDb()]
        );
        if ($n !== 1) {
            return false;
        }
        self::movement($skuId, $orderId, 'reserve', 0, $qty, null, $transitionKey);
        return true;
    }

    public static function release(int $skuId, int $qty, int $orderId, string $transitionKey, ?string $reason = null): void
    {
        $n = Db::exec('UPDATE inventory SET reserved = reserved - :q, updated_at = :t WHERE sku_id = :s AND reserved >= :q2',
            ['q' => $qty, 'q2' => $qty, 's' => $skuId, 't' => Clock::nowDb()]);
        if ($n !== 1) {
            throw new \RuntimeException("Không thể giải phóng tồn giữ SKU $skuId");
        }
        self::movement($skuId, $orderId, 'release', 0, -$qty, $reason, $transitionKey);
    }

    /** Bàn giao: trừ tồn thực tế và tồn đang giữ. */
    public static function ship(int $skuId, int $qty, int $orderId, string $transitionKey): void
    {
        $n = Db::exec('UPDATE inventory SET on_hand = on_hand - :q, reserved = reserved - :q2, updated_at = :t WHERE sku_id = :s AND reserved >= :q3 AND on_hand >= :q4',
            ['q' => $qty, 'q2' => $qty, 'q3' => $qty, 'q4' => $qty, 's' => $skuId, 't' => Clock::nowDb()]);
        if ($n !== 1) {
            throw new \RuntimeException("Không thể xuất kho SKU $skuId");
        }
        self::movement($skuId, $orderId, 'ship', -$qty, -$qty, 'Bàn giao vận chuyển', $transitionKey);
    }

    /** Hàng trả về: chỉ cộng tồn bán được cho số lượng kiểm đạt. */
    public static function returnInspected(int $skuId, int $okQty, int $rejectQty, int $orderId, string $transitionKey, ?string $reason): void
    {
        if ($okQty > 0) {
            Db::exec('UPDATE inventory SET on_hand = on_hand + :q, updated_at = :t WHERE sku_id = :s', ['q' => $okQty, 's' => $skuId, 't' => Clock::nowDb()]);
            self::movement($skuId, $orderId, 'return_restock', $okQty, 0, $reason, $transitionKey);
        }
        if ($rejectQty > 0) {
            self::movement($skuId, $orderId, 'return_reject', 0, 0, trim('Không đạt kiểm: ' . $rejectQty . ' đv. ' . ($reason ?? '')), $transitionKey . ':rej');
        }
    }

    /** Điều chỉnh thủ công / nhập kho — bắt buộc số lượng và lý do (FR-06). */
    public static function adjust(int $skuId, int $delta, string $type, string $reason): void
    {
        Auth::require('inventory.manage');
        $reason = trim($reason);
        if ($delta === 0 || $reason === '' || !in_array($type, ['receive', 'adjust'], true)) {
            throw ApiError::validation(['delta' => $delta === 0 ? 'Nhập số lượng khác 0' : null, 'reason' => $reason === '' ? 'Bắt buộc ghi lý do' : null]);
        }
        if ($type === 'receive' && $delta < 0) {
            throw ApiError::validation(['delta' => 'Nhập kho phải là số dương']);
        }
        Db::tx(function () use ($skuId, $delta, $type, $reason) {
            $before = Db::one('SELECT * FROM inventory WHERE sku_id = :s FOR UPDATE', ['s' => $skuId]);
            if (!$before) {
                throw ApiError::notFound('SKU không tồn tại.');
            }
            if ((int)$before['on_hand'] + $delta < (int)$before['reserved']) {
                throw new ApiError('INVENTORY_BELOW_RESERVED', 'Không thể giảm tồn thực tế xuống dưới số đang giữ cho đơn (' . $before['reserved'] . ').', 422);
            }
            Db::exec('UPDATE inventory SET on_hand = on_hand + :d, updated_at = :t WHERE sku_id = :s', ['d' => $delta, 's' => $skuId, 't' => Clock::nowDb()]);
            self::movement($skuId, null, $type, $delta, 0, $reason, null);
            $after = Db::one('SELECT * FROM inventory WHERE sku_id = :s', ['s' => $skuId]);
            Audit::log('inventory.' . $type, 'sku', (string)$skuId, $before, $after, $reason);
        });
    }

    public static function movement(int $skuId, ?int $orderId, string $type, int $onHandDelta, int $reservedDelta, ?string $reason, ?string $transitionKey): void
    {
        $inv = Db::one('SELECT on_hand, reserved FROM inventory WHERE sku_id = :s', ['s' => $skuId]);
        Db::insert('inventory_movements', [
            'sku_id'         => $skuId,
            'order_id'       => $orderId,
            'type'           => $type,
            'on_hand_delta'  => $onHandDelta,
            'reserved_delta' => $reservedDelta,
            'on_hand_after'  => (int)$inv['on_hand'],
            'reserved_after' => (int)$inv['reserved'],
            'reason'         => $reason,
            'transition_key' => $transitionKey,
            'user_id'        => Auth::id(),
            'created_at'     => Clock::nowDb(),
        ]);
    }

    public static function available(int $skuId): int
    {
        return (int)Db::val('SELECT on_hand - reserved FROM inventory WHERE sku_id = :s', ['s' => $skuId]);
    }
}
