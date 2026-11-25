<?php
$levelCls = ['ok' => 'bg-tea', 'warn' => 'bg-turmeric', 'bad' => 'bg-alert'];
?>
<div class="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
  <a href="/admin/orders?status=pending" class="a-card no-underline hover:ring-2 hover:ring-tea/30">
    <p class="text-sm text-ink-soft">Đơn chờ xác nhận</p>
    <p class="mt-1 text-3xl font-extrabold text-ink tabular-nums"><?= $kpi['pending'] ?></p>
    <p class="mt-1 text-sm text-ink-mute"><?= $kpi['qr_wait'] ?> đơn VietQR chưa đủ tiền<?= $kpi['review'] ? ', ' . $kpi['review'] . ' đơn cần xem lại' : '' ?></p>
  </a>
  <a href="/admin/orders?status=confirmed" class="a-card no-underline hover:ring-2 hover:ring-tea/30">
    <p class="text-sm text-ink-soft">Đã xác nhận, chờ bàn giao</p>
    <p class="mt-1 text-3xl font-extrabold text-ink tabular-nums"><?= $kpi['to_ship'] ?></p>
  </a>
  <div class="a-card">
    <p class="text-sm text-ink-soft">Hôm nay</p>
    <p class="mt-1 text-3xl font-extrabold tabular-nums"><?= money($kpi['revenue_today']) ?></p>
    <p class="mt-1 text-sm text-ink-mute"><?= $kpi['orders_today'] ?> đơn mới (không tính đơn hủy)</p>
  </div>
</div>

<div class="mt-6 grid gap-6 xl:grid-cols-[1fr_380px]">
  <section class="a-card overflow-x-auto">
    <div class="flex items-center justify-between"><h2 class="text-lg">Đơn gần đây</h2><a href="/admin/orders" class="text-sm font-semibold">Tất cả đơn</a></div>
    <?php if (!$recent): ?><p class="mt-4 text-sm text-ink-mute">Chưa có đơn hàng, hoặc bạn không có quyền xem đơn.</p><?php else: ?>
    <table class="a-table mt-3">
      <thead><tr><th>Mã đơn</th><th>Khách</th><th class="text-right">Tổng</th><th>Trạng thái</th><th>Thanh toán</th><th>Lúc đặt</th></tr></thead>
      <tbody>
      <?php foreach ($recent as $o): ?>
        <tr>
          <td><a href="/admin/orders/<?= $o['id'] ?>" class="font-semibold"><?= e($o['code']) ?></a></td>
          <td><?= e($o['ship_name']) ?></td>
          <td class="text-right tabular-nums"><?= money($o['total']) ?></td>
          <td><?= status_badge($o['status']) ?></td>
          <td><span class="text-xs font-semibold uppercase text-ink-mute"><?= e($o['payment_method']) ?></span> <?= status_badge($o['payment_status']) ?></td>
          <td class="whitespace-nowrap text-ink-mute"><?= vn_time($o['created_at']) ?></td>
        </tr>
      <?php endforeach; ?>
      </tbody>
    </table>
    <?php endif; ?>
  </section>

  <div class="space-y-6">
    <section class="a-card">
      <h2 class="text-lg">Tình trạng hệ thống</h2>
      <ul class="mt-3 space-y-2 text-sm">
        <?php foreach ($health as $h): ?>
          <li class="flex items-start gap-2"><span class="mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full <?= $levelCls[$h['level']] ?>" aria-hidden="true"></span><span class="flex-1"><?= e($h['name']) ?><br><span class="text-ink-mute"><?= e($h['value']) ?></span></span></li>
        <?php endforeach; ?>
      </ul>
    </section>
    <section class="a-card">
      <div class="flex items-center justify-between"><h2 class="text-lg">Sắp hết hàng</h2><?php if (can('inventory.manage')): ?><a href="/admin/inventory?low=1" class="text-sm font-semibold">Tồn kho</a><?php endif; ?></div>
      <ul class="mt-3 divide-y divide-ink/5 text-sm">
        <?php foreach ($low as $s): ?>
          <li class="flex justify-between gap-2 py-1.5"><span><?= e($s['name']) ?> <span class="text-ink-mute"><?= e($s['variant_label']) ?></span></span><span class="font-bold tabular-nums <?= $s['available'] <= 0 ? 'text-alert' : 'text-coffee' ?>"><?= (int)$s['available'] ?></span></li>
        <?php endforeach; ?>
        <?php if (!$low): ?><li class="py-1.5 text-ink-mute">Tất cả SKU còn trên 10.</li><?php endif; ?>
      </ul>
    </section>
    <?php $todo = array_filter(['Sai lệch thanh toán' => ['/admin/discrepancies', $counts['discrepancies'] ?? 0], 'Hoàn tiền chờ chuyển' => ['/admin/refunds', $counts['refunds'] ?? 0], 'Nội dung chờ duyệt' => ['/admin/content?kind=faq&status=pending_review', $counts['faq_review'] ?? 0], 'Gợi ý mua kèm chờ duyệt' => ['/admin/crosssell', $counts['crosssell'] ?? 0], 'Khách đến kỳ mua lại' => ['/admin/care', $counts['care'] ?? 0]], fn($x) => $x[1] > 0); ?>
    <?php if ($todo): ?>
    <section class="a-card">
      <h2 class="text-lg">Việc cần xử lý</h2>
      <ul class="mt-3 space-y-1 text-sm">
        <?php foreach ($todo as $label => [$href, $n]): ?><li class="flex justify-between"><a href="<?= e($href) ?>"><?= e($label) ?></a><span class="font-bold"><?= (int)$n ?></span></li><?php endforeach; ?>
      </ul>
    </section>
    <?php endif; ?>
  </div>
</div>
