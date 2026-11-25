<?php
use App\Domain\OrderService;
use App\Domain\PaymentService;

$next = [];
foreach (OrderService::TRANSITIONS as $k => $perm) {
    [$from, $to] = explode('>', $k);
    if ($from === $o['status'] && can($perm)) $next[$to] = OrderService::STATUS_LABELS[$to];
}
$net = (int)$o['amount_received'] - (int)$o['amount_refunded'];
$mvLabel = ['reserve' => 'Giữ tồn', 'release' => 'Giải phóng', 'ship' => 'Xuất kho', 'return_restock' => 'Nhập lại (đạt)', 'return_reject' => 'Không đạt kiểm', 'adjust' => 'Điều chỉnh', 'receive' => 'Nhập kho'];
?>
<div class="flex flex-wrap items-center gap-3">
  <a href="/admin/orders" class="text-sm">← Danh sách đơn</a>
  <?= status_badge($o['status']) ?> <?= status_badge($o['payment_status']) ?>
  <span class="text-sm text-ink-mute"><?= strtoupper(e($o['payment_method'])) ?>, đặt lúc <?= vn_time($o['created_at']) ?></span>
</div>
<?php if ($o['needs_review']): ?>
  <div class="mt-4 rounded-lg border border-alert/30 bg-alert-light p-4 text-sm text-alert" role="alert"><strong>Cần xem lại:</strong> <?= e($o['review_reason']) ?>. Kiểm tra khoản thu/sai lệch rồi xác nhận hoặc hủy đơn (tạo hoàn tiền nếu cần).</div>
<?php endif; ?>

<div class="mt-4 grid gap-6 xl:grid-cols-[1fr_400px]">
  <div class="space-y-6">
    <section class="a-card overflow-x-auto">
      <h2 class="text-lg">Dòng hàng (bản chụp lúc đặt)</h2>
      <table class="a-table mt-3">
        <thead><tr><th>Sản phẩm</th><th>SKU</th><th class="text-right">Đơn giá</th><th class="text-right">SL</th><th class="text-right">Thành tiền</th><?php if (in_array($o['status'], ['returned'], true)): ?><th>Kiểm hoàn</th><?php endif; ?></tr></thead>
        <tbody>
        <?php foreach ($items as $it): ?>
          <tr>
            <td><?= e($it['product_name']) ?><br><span class="text-ink-mute"><?= e($it['variant_label']) ?></span></td>
            <td class="font-mono text-xs"><?= e($it['sku_code']) ?></td>
            <td class="text-right tabular-nums"><?= money($it['unit_price']) ?><?php if ($it['unit_price'] < $it['list_price']): ?><br><span class="price-was text-xs"><?= money($it['list_price']) ?></span> <span class="chip-sale">FS</span><?php endif; ?></td>
            <td class="text-right"><?= (int)$it['quantity'] ?></td>
            <td class="text-right font-semibold tabular-nums"><?= money($it['line_total']) ?></td>
            <?php if ($o['status'] === 'returned'): ?><td class="text-xs">Đạt <?= (int)$it['qty_returned_ok'] ?>, hỏng <?= (int)$it['qty_returned_reject'] ?></td><?php endif; ?>
          </tr>
        <?php endforeach; ?>
        </tbody>
      </table>
      <dl class="ml-auto mt-4 max-w-xs space-y-1 text-sm">
        <div class="flex justify-between"><dt>Tiền hàng sau Flash Sale</dt><dd class="tabular-nums"><?= money($o['goods_subtotal']) ?></dd></div>
        <div class="flex justify-between"><dt>Voucher <?= e($o['voucher_code'] ?? '') ?><?= $voucher ? ' (' . e($voucher['status']) . ')' : '' ?></dt><dd class="tabular-nums">−<?= money($o['voucher_discount']) ?></dd></div>
        <div class="flex justify-between"><dt>Phí giao (<?= e($o['zone_name']) ?>)</dt><dd class="tabular-nums"><?= money($o['shipping_fee']) ?></dd></div>
        <div class="flex justify-between border-t border-ink/10 pt-1 text-base font-bold"><dt>Tổng</dt><dd class="tabular-nums"><?= money($o['total']) ?></dd></div>
        <?php if ($canPay): ?>
        <div class="flex justify-between text-ink-soft"><dt>Đã thu</dt><dd class="tabular-nums"><?= money($o['amount_received']) ?></dd></div>
        <div class="flex justify-between text-ink-soft"><dt>Đã hoàn</dt><dd class="tabular-nums"><?= money($o['amount_refunded']) ?></dd></div>
        <?php endif; ?>
      </dl>
    </section>

    <?php if ($canPay): ?>
    <section class="a-card overflow-x-auto">
      <h2 class="text-lg">Lịch sử tài chính</h2>
      <table class="a-table mt-3">
        <thead><tr><th>Loại</th><th>Nguồn / mã giao dịch</th><th class="text-right">Số tiền</th><th>Thời điểm</th><th>Người ghi nhận</th></tr></thead>
        <tbody>
        <?php foreach ($receipts as $r): ?><tr><td>Khoản thu <?= strtoupper(e($r['method'])) ?></td><td><?= e($r['source']) ?> / <span class="font-mono text-xs"><?= e($r['bank_txn_id']) ?></span><?php if ($r['transfer_content']): ?><br><span class="text-xs text-ink-mute">ND: <?= e($r['transfer_content']) ?></span><?php endif; ?></td><td class="text-right tabular-nums text-tea">+<?= money($r['amount']) ?></td><td><?= vn_time($r['received_at']) ?></td><td><?= e($r['full_name']) ?></td></tr><?php endforeach; ?>
        <?php foreach ($refunds as $r): ?><tr><td>Hoàn tiền <?= status_badge($r['status'], ['pending' => 'Chờ chuyển', 'completed' => 'Đã hoàn', 'cancelled' => 'Đã hủy'][$r['status']]) ?></td><td><?= e($r['reason']) ?><?php if ($r['refund_txn_ref']): ?><br><span class="font-mono text-xs"><?= e($r['refund_txn_ref']) ?></span><?php endif; ?></td><td class="text-right tabular-nums text-alert">−<?= money($r['amount']) ?></td><td><?= vn_time($r['refunded_at'] ?? $r['created_at']) ?></td><td><?= e($r['approver'] ?? '') ?></td></tr><?php endforeach; ?>
        <?php if (!$receipts && !$refunds): ?><tr><td colspan="5" class="text-ink-mute">Chưa có giao dịch.</td></tr><?php endif; ?>
        </tbody>
      </table>
      <?php if ($discs): ?>
        <h3 class="mt-4 font-semibold">Sai lệch</h3>
        <ul class="mt-2 space-y-1 text-sm">
          <?php foreach ($discs as $d): ?><li><?= status_badge($d['status']) ?> <?= e(PaymentService::DISCREPANCY_LABELS[$d['type']]) ?><?= $d['expected_amount'] !== null ? ': cần ' . money($d['expected_amount']) . ', nhận ' . money($d['actual_amount']) : '' ?><?= $d['resolution_note'] ? ' — ' . e($d['resolution_note']) : '' ?> <?php if ($d['status'] === 'open' && can('payments.reconcile')): ?><a href="/admin/discrepancies#d<?= $d['id'] ?>">Xử lý</a><?php endif; ?></li><?php endforeach; ?>
        </ul>
      <?php endif; ?>
    </section>
    <?php endif; ?>

    <section class="a-card">
      <h2 class="text-lg">Lịch sử trạng thái</h2>
      <ol class="mt-3 space-y-2 border-l-2 border-jade-200 pl-4 text-sm">
        <?php foreach ($history as $h): ?>
          <li><span class="font-semibold"><?= e(OrderService::STATUS_LABELS[$h['to_status']] ?? $h['to_status']) ?></span>
            <span class="text-ink-mute">— <?= vn_time($h['created_at'], 'd/m/Y H:i:s') ?>, <?= e($h['actor_type'] === 'customer' ? 'khách hàng' : ($h['actor_type'] === 'system' ? 'hệ thống' : ($h['full_name'] ?? 'nhân viên'))) ?></span>
            <?php if ($h['reason']): ?><br><span class="text-ink-soft"><?= e($h['reason']) ?></span><?php endif; ?></li>
        <?php endforeach; ?>
      </ol>
      <?php if ($movements): ?>
        <h3 class="mt-5 font-semibold">Biến động kho của đơn</h3>
        <ul class="mt-2 space-y-0.5 text-xs text-ink-soft">
          <?php foreach ($movements as $m): ?><li><?= vn_time($m['created_at']) ?> — <?= e($mvLabel[$m['type']] ?? $m['type']) ?> <span class="font-mono"><?= e($m['sku_code']) ?></span>: thực tế <?= sprintf('%+d', $m['on_hand_delta']) ?>, giữ <?= sprintf('%+d', $m['reserved_delta']) ?> (còn <?= (int)$m['on_hand_after'] ?>/<?= (int)$m['reserved_after'] ?>)</li><?php endforeach; ?>
        </ul>
      <?php endif; ?>
    </section>
  </div>

  <div class="space-y-6">
    <section class="a-card">
      <h2 class="text-lg">Giao đến</h2>
      <p class="mt-2 font-semibold"><?= e($o['ship_name']) ?> — <a href="tel:<?= e($o['ship_phone']) ?>"><?= e($o['ship_phone']) ?></a></p>
      <p class="text-sm text-ink-soft"><?= e($o['ship_address']) ?>, <?= e($o['ship_province']) ?></p>
      <?php if ($o['ship_note']): ?><p class="mt-2 rounded bg-turmeric-light px-2 py-1 text-sm">Ghi chú: <?= e($o['ship_note']) ?></p><?php endif; ?>
      <p class="mt-2 text-sm"><?= $o['account_id'] ? 'Tài khoản: <strong>' . e($o['account_name']) . '</strong>' . ($o['account_email'] ? ' (' . e($o['account_email']) . ')' : '') . ' — ' . e(str_replace(['google', 'facebook', ','], ['Google', 'Facebook', ', '], (string)$o['account_providers'])) : '<span class="text-ink-mute">Khách đặt không đăng nhập</span>' ?></p>
      <p class="mt-2 text-xs text-ink-mute">Đồng ý nhận tiếp thị: <?= $o['marketing_consent'] ? 'Có' : 'Không' ?>. Nội dung CK: <strong><?= e($o['transfer_content']) ?></strong>. Khách xem trang xác nhận: <?= $o['qr_viewed_at'] ? vn_time($o['qr_viewed_at']) : 'chưa' ?>.</p>
    </section>

    <?php if ($next): ?>
    <section class="a-card">
      <h2 class="text-lg">Xử lý đơn</h2>
      <form method="post" action="/admin/orders/<?= $o['id'] ?>/transition" class="mt-3 space-y-3">
        <?= csrf_field() ?>
        <div><label class="label" for="to">Chuyển sang</label>
          <select id="to" name="to" class="field" data-reveal><?php foreach ($next as $k => $v): ?><option value="<?= $k ?>"><?= e($v) ?></option><?php endforeach; ?></select></div>
        <div class="hidden space-y-3" data-reveal-for="to" data-reveal-when="shipping">
          <?= a_field('carrier_name', 'Đơn vị vận chuyển', $o['carrier_name'] ?? '', $errors) ?>
          <?= a_field('tracking_code', 'Mã vận đơn', $o['tracking_code'] ?? '', $errors) ?>
          <p class="text-xs text-ink-mute">Bàn giao sẽ trừ tồn thực tế và tồn đang giữ; voucher chuyển sang đã dùng.</p>
        </div>
        <?php if ($o['status'] === 'returning'): ?>
        <div class="space-y-2" data-reveal-for="to" data-reveal-when="returned">
          <p class="label">Kiểm hàng khi kho nhận lại</p>
          <?php foreach ($items as $it): ?>
            <div class="grid grid-cols-[1fr_70px_70px] items-center gap-2 text-sm">
              <span><?= e($it['sku_code']) ?> <span class="text-ink-mute">(giao <?= (int)$it['quantity'] ?>)</span></span>
              <label class="sr-only" for="ok<?= $it['id'] ?>">Đạt</label><input id="ok<?= $it['id'] ?>" type="number" min="0" max="<?= (int)$it['quantity'] ?>" name="inspection[<?= $it['id'] ?>][ok]" value="<?= (int)$it['quantity'] ?>" class="field py-1.5" title="Số lượng đạt, cộng lại tồn bán được">
              <label class="sr-only" for="rj<?= $it['id'] ?>">Hỏng</label><input id="rj<?= $it['id'] ?>" type="number" min="0" max="<?= (int)$it['quantity'] ?>" name="inspection[<?= $it['id'] ?>][reject]" value="0" class="field py-1.5" title="Số lượng không đạt">
            </div>
          <?php endforeach; ?>
          <p class="text-xs text-ink-mute">Cột 1: số đạt (cộng lại tồn bán được). Cột 2: số hỏng.</p>
        </div>
        <?php endif; ?>
        <?= a_field('reason', 'Lý do / ghi chú', '', $errors, ['type' => 'textarea', 'rows' => 2, 'hint' => 'Bắt buộc khi hủy hoặc hoàn hàng.']) ?>
        <?php if ($o['payment_method'] === 'vietqr' && $o['status'] === 'pending' && (int)$o['amount_received'] < (int)$o['total']): ?>
          <p class="rounded bg-turmeric-light px-3 py-2 text-xs">Đơn VietQR chỉ xác nhận được sau khi đối soát đủ <?= money($o['total']) ?> và xử lý hết sai lệch.</p>
        <?php endif; ?>
        <button class="btn-primary w-full">Cập nhật trạng thái</button>
      </form>
    </section>
    <?php endif; ?>

    <?php if (can('orders.process') && in_array($o['status'], ['shipping', 'delivered', 'confirmed'], true)): ?>
    <section class="a-card">
      <h2 class="text-lg">Vận đơn</h2>
      <form method="post" action="/admin/orders/<?= $o['id'] ?>/tracking" class="mt-3 space-y-3"><?= csrf_field() ?>
        <?= a_field('carrier_name', 'Đơn vị vận chuyển', $o['carrier_name'] ?? '', $errors) ?>
        <?= a_field('tracking_code', 'Mã vận đơn', $o['tracking_code'] ?? '', $errors) ?>
        <button class="btn-ghost w-full">Lưu vận đơn</button>
      </form>
    </section>
    <?php endif; ?>

    <?php if (can('payments.reconcile') && $o['payment_method'] === 'cod' && in_array($o['status'], ['delivered', 'returning', 'returned'], true) && (int)$o['amount_received'] < (int)$o['total']): ?>
    <section class="a-card">
      <h2 class="text-lg">Đối soát COD</h2>
      <form method="post" action="/admin/orders/<?= $o['id'] ?>/cod" class="mt-3 space-y-3"><?= csrf_field() ?>
        <?= a_field('amount', 'Số tiền thực nhận', $old['amount'] ?? ((int)$o['total'] - (int)$o['amount_received']), $errors, ['type' => 'number']) ?>
        <?= a_field('source', 'Nguồn (người giao / hãng)', $old['source'] ?? ($o['carrier_name'] ?: 'COD'), $errors) ?>
        <?= a_field('bank_txn_id', 'Mã bảng kê / giao dịch', $old['bank_txn_id'] ?? '', $errors) ?>
        <?= a_field('received_at', 'Thời điểm nhận', $old['received_at'] ?? \App\Core\Clock::toLocalInput(\App\Core\Clock::nowDb()), $errors, ['type' => 'datetime-local']) ?>
        <button class="btn-primary w-full">Ghi nhận đã thu</button>
      </form>
    </section>
    <?php endif; ?>

    <?php if (can('refunds.approve') && $net > 0): ?>
    <section class="a-card">
      <h2 class="text-lg">Tạo hoàn tiền</h2>
      <p class="text-xs text-ink-mute">Thực nhận còn lại: <?= money($net) ?>. Tổng hoàn không vượt tiền thực nhận.</p>
      <form method="post" action="/admin/orders/<?= $o['id'] ?>/refund" class="mt-3 space-y-3"><?= csrf_field() ?>
        <?= a_field('refund_amount', 'Số tiền hoàn', $old['refund_amount'] ?? '', $errors, ['type' => 'number']) ?>
        <?= a_field('reason', 'Lý do', $old['reason'] ?? '', $errors) ?>
        <button class="btn-ghost w-full">Tạo yêu cầu hoàn</button>
      </form>
    </section>
    <?php endif; ?>
  </div>
</div>
