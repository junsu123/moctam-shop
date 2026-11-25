<p class="max-w-3xl text-sm text-ink-soft">Yêu cầu hoàn được tạo khi hủy đơn đã thu tiền, khi xử lý sai lệch, hoặc thủ công trên trang đơn. Người có quyền duyệt hoàn ghi nhận mã giao dịch hoàn sau khi chuyển tiền. Tổng hoàn không vượt tổng tiền thực nhận.</p>
<div class="mt-4 space-y-3">
  <?php foreach ($rows as $r): ?>
    <section class="a-card">
      <div class="flex flex-wrap items-center gap-3">
        <?= status_badge($r['status'], ['pending' => 'Chờ chuyển', 'completed' => 'Đã hoàn', 'cancelled' => 'Đã hủy'][$r['status']]) ?>
        <a href="/admin/orders/<?= $r['order_id'] ?>" class="font-mono font-semibold"><?= e($r['code']) ?></a>
        <span class="text-sm"><?= e($r['ship_name']) ?></span>
        <span class="ml-auto text-xl font-extrabold tabular-nums"><?= money($r['amount']) ?></span>
      </div>
      <p class="mt-1 text-sm text-ink-soft"><?= e($r['reason']) ?> — tạo lúc <?= vn_time($r['created_at']) ?>. Đơn đã thu <?= money($r['amount_received']) ?>, đã hoàn <?= money($r['amount_refunded']) ?>.</p>
      <?php if ($r['status'] === 'completed'): ?>
        <p class="mt-1 text-sm">Đã hoàn lúc <?= vn_time($r['refunded_at']) ?>, mã GD <span class="font-mono"><?= e($r['refund_txn_ref']) ?></span>, người duyệt <?= e($r['approver']) ?>.</p>
      <?php elseif ($r['status'] === 'pending' && can('refunds.approve')): ?>
        <div class="mt-3 flex flex-wrap items-end gap-3">
          <form method="post" action="/admin/refunds/<?= $r['id'] ?>/complete" class="flex flex-wrap items-end gap-3"><?= csrf_field() ?>
            <?= a_field('refund_txn_ref', 'Mã giao dịch hoàn', '', $errors) ?>
            <?= a_field('refunded_at', 'Thời điểm chuyển', \App\Core\Clock::toLocalInput(\App\Core\Clock::nowDb()), [], ['type' => 'datetime-local']) ?>
            <button class="btn-primary">Duyệt & ghi nhận đã hoàn</button>
          </form>
          <form method="post" action="/admin/refunds/<?= $r['id'] ?>/cancel" data-confirm="Hủy yêu cầu hoàn này?"><?= csrf_field() ?><button class="btn-ghost">Hủy yêu cầu</button></form>
        </div>
      <?php endif; ?>
    </section>
  <?php endforeach; ?>
  <?php if (!$rows): ?><div class="a-card text-ink-mute">Chưa có yêu cầu hoàn tiền.</div><?php endif; ?>
</div>
