<?php use App\Domain\PaymentService; ?>
<nav class="flex gap-1 text-sm">
  <a href="?status=open" class="rounded-md px-3 py-1.5 no-underline <?= $st !== 'resolved' ? 'bg-tea text-white font-semibold' : 'bg-white text-ink' ?>">Đang mở</a>
  <a href="?status=resolved" class="rounded-md px-3 py-1.5 no-underline <?= $st === 'resolved' ? 'bg-tea text-white font-semibold' : 'bg-white text-ink' ?>">Đã xử lý</a>
</nav>
<p class="mt-3 max-w-3xl text-sm text-ink-soft">Với tiền đến sau khi đơn đã hủy: kiểm tra còn hàng và xác nhận với khách trước khi chọn "Tạo đơn thay thế" hoặc "Hoàn tiền".</p>
<div class="mt-4 space-y-4">
  <?php foreach ($rows as $d): ?>
    <section class="a-card" id="d<?= $d['id'] ?>">
      <div class="flex flex-wrap items-center gap-3">
        <?= status_badge($d['status']) ?>
        <span class="font-bold"><?= e(PaymentService::DISCREPANCY_LABELS[$d['type']]) ?></span>
        <?php if ($d['code']): ?><a href="/admin/orders/<?= $d['order_id'] ?>" class="font-mono"><?= e($d['code']) ?></a> <?= status_badge($d['order_status']) ?><?php endif; ?>
        <span class="ml-auto text-sm text-ink-mute"><?= vn_time($d['created_at']) ?></span>
      </div>
      <p class="mt-2 text-sm">
        Giao dịch <span class="font-mono"><?= e($d['bank_txn_id']) ?></span> (<?= e($d['source']) ?>, <?= vn_time($d['received_at']) ?>): <strong><?= money($d['actual_amount']) ?></strong>
        <?php if ($d['expected_amount'] !== null): ?> — đơn cần <?= money($d['expected_amount']) ?>, đã nhận tổng <?= money($d['amount_received']) ?><?php endif; ?>
        <?php if ($d['transfer_content']): ?><br>Nội dung: <em><?= e($d['transfer_content']) ?></em><?php endif; ?>
      </p>
      <?php if ($d['status'] === 'resolved'): ?>
        <p class="mt-2 text-sm text-ink-soft">Đã xử lý (<?= e($d['resolution']) ?>) bởi <?= e($d['full_name']) ?> lúc <?= vn_time($d['resolved_at']) ?>: <?= e($d['resolution_note']) ?></p>
      <?php else: ?>
        <form method="post" action="/admin/discrepancies/<?= $d['id'] ?>/resolve" class="mt-3 grid gap-3 sm:grid-cols-4"><?= csrf_field() ?>
          <?= a_field('resolution', 'Hướng xử lý', '', [], ['type' => 'select', 'attrs' => 'data-reveal', 'options' => ['accepted' => 'Chấp nhận (đã đủ/hợp lệ)', 'customer_topup' => 'Khách chuyển bổ sung', 'refund' => 'Hoàn tiền cho khách', 'replacement_order' => 'Tạo đơn thay thế', 'other' => 'Khác']]) ?>
          <?php if ($d['type'] === 'unmatched'): ?><?= a_field('link_order_code', 'Gắn vào đơn', '', [], ['class' => 'uppercase font-mono']) ?><?php endif; ?>
          <div class="hidden" data-reveal-for="resolution" data-reveal-when="refund"><?= a_field('refund_amount', 'Số tiền hoàn', $d['type'] === 'overpaid' ? max(0, (int)$d['amount_received'] - (int)$d['expected_amount']) : $d['actual_amount'], [], ['type' => 'number']) ?></div>
          <?= a_field('resolution_note', 'Nội dung đã thống nhất với khách', '', [], ['wrap' => 'sm:col-span-2']) ?>
          <div class="flex items-end"><button class="btn-primary w-full">Xử lý</button></div>
        </form>
      <?php endif; ?>
    </section>
  <?php endforeach; ?>
  <?php if (!$rows): ?><div class="a-card text-ink-mute">Không có sai lệch <?= $st === 'resolved' ? 'đã xử lý' : 'đang mở' ?>.</div><?php endif; ?>
</div>
