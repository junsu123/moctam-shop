<?php
$levelCls = ['ok' => 'bg-tea', 'warn' => 'bg-turmeric', 'bad' => 'bg-alert'];
$canOrders = can('orders.view');
// Việc cần làm: chỉ mục người dùng có quyền (navCounts đã lọc theo quyền), chỉ hiện mục còn việc
$todo = array_filter([
    ['Đơn chờ xác nhận', '/admin/orders?status=pending', $canOrders ? $kpi['pending'] : 0, $kpi['qr_wait'] ? $kpi['qr_wait'] . ' đơn VietQR chưa đủ tiền' : 'Gọi xác nhận hoặc đối soát'],
    ['Đơn cần xem lại', '/admin/orders?status=review', $canOrders ? $kpi['review'] : 0, 'Có tiền về sau khi hết hạn hoặc sai lệch'],
    ['Chờ bàn giao vận chuyển', '/admin/orders?status=confirmed', $canOrders ? $kpi['to_ship'] : 0, 'Đóng gói và nhập mã vận đơn'],
    ['Sai lệch thanh toán', '/admin/discrepancies', $counts['discrepancies'] ?? 0, 'Thiếu, thừa, sai nội dung chuyển khoản'],
    ['Hoàn tiền chờ chuyển', '/admin/refunds', $counts['refunds'] ?? 0, 'Chuyển tiền rồi ghi mã giao dịch'],
    ['Nội dung chờ duyệt', '/admin/content?kind=faq&status=pending_review', $counts['faq_review'] ?? 0, 'Bản nháp FAQ, blog, trang chính sách'],
    ['Gợi ý mua kèm chờ duyệt', '/admin/crosssell', $counts['crosssell'] ?? 0, 'Do dịch vụ AI đề xuất'],
    ['Khách đến kỳ mua lại', '/admin/care', $counts['care'] ?? 0, 'Danh sách chăm sóc lại'],
], fn($t) => $t[2] > 0);
$issues = array_filter($health, fn($h) => $h['level'] !== 'ok');
?>
<section aria-labelledby="todo-h">
  <div class="flex items-baseline justify-between gap-3">
    <h2 id="todo-h" class="text-lg">Việc cần làm</h2>
    <span class="text-sm text-ink-mute"><?= vn_time(\App\Core\Clock::nowDb(), 'H:i, d/m/Y') ?></span>
  </div>
  <?php if ($todo): ?>
    <ul class="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      <?php foreach ($todo as [$label, $href, $n, $hint]): ?>
        <li><a href="<?= e($href) ?>" class="flex h-full items-start gap-4 rounded-xl border border-turmeric/40 bg-white p-4 text-ink no-underline hover:border-turmeric hover:bg-turmeric-light/40">
          <span class="min-w-[2.75rem] rounded-lg bg-turmeric px-2 py-1 text-center text-xl font-extrabold tabular-nums text-ink"><?= (int)$n ?></span>
          <span><span class="block font-semibold"><?= e($label) ?></span><span class="mt-0.5 block text-sm text-ink-mute"><?= e($hint) ?></span></span>
        </a></li>
      <?php endforeach; ?>
    </ul>
  <?php else: ?>
    <p class="mt-3 rounded-xl border border-tea/20 bg-white p-4 text-ink-soft">Không còn việc tồn. Đơn mới và các mục cần duyệt sẽ hiện ở đây.</p>
  <?php endif; ?>
</section>

<div class="mt-6 grid gap-6 xl:grid-cols-[1fr_360px]">
  <section class="a-card min-w-0 p-0">
    <div class="flex items-center justify-between px-4 pt-4 sm:px-5"><h2 class="text-lg">Đơn gần đây</h2><?php if ($canOrders): ?><a href="/admin/orders" class="text-sm font-semibold">Tất cả đơn</a><?php endif; ?></div>
    <?php if (!$recent): ?><p class="px-5 pb-5 pt-3 text-sm text-ink-mute"><?= $canOrders ? 'Chưa có đơn hàng.' : 'Bạn chưa được cấp quyền xem đơn.' ?></p><?php else: ?>
    <div class="mt-3 overflow-x-auto">
    <table class="a-table">
      <thead><tr><th>Mã đơn</th><th class="hidden sm:table-cell">Khách</th><th class="text-right">Tổng</th><th>Trạng thái</th><th class="hidden md:table-cell">Lúc đặt</th></tr></thead>
      <tbody>
      <?php foreach ($recent as $o): ?>
        <tr data-href="/admin/orders/<?= (int)$o['id'] ?>">
          <td class="whitespace-nowrap"><a href="/admin/orders/<?= (int)$o['id'] ?>" class="font-semibold"><?= e($o['code']) ?></a></td>
          <td class="hidden sm:table-cell"><?= e($o['ship_name']) ?></td>
          <td class="text-right font-semibold tabular-nums"><?= money($o['total']) ?></td>
          <td class="whitespace-nowrap"><?= status_badge($o['status']) ?> <span class="hidden sm:inline"><?= status_badge($o['payment_status']) ?></span></td>
          <td class="hidden whitespace-nowrap text-ink-mute md:table-cell"><?= vn_time($o['created_at']) ?></td>
        </tr>
      <?php endforeach; ?>
      </tbody>
    </table>
    </div>
    <?php endif; ?>
  </section>

  <div class="space-y-6">
    <section class="a-card">
      <h2 class="text-lg">Hôm nay</h2>
      <p class="mt-2 text-3xl font-extrabold tabular-nums"><?= money($kpi['revenue_today']) ?></p>
      <p class="mt-1 text-sm text-ink-mute"><?= (int)$kpi['orders_today'] ?> đơn mới, không tính đơn đã hủy</p>
    </section>

    <section class="a-card">
      <div class="flex items-center justify-between"><h2 class="text-lg">Sắp hết hàng</h2><?php if (can('inventory.manage')): ?><a href="/admin/inventory?low=1" class="text-sm font-semibold">Nhập kho</a><?php endif; ?></div>
      <ul class="mt-2 divide-y divide-ink/5 text-sm">
        <?php foreach ($low as $s): ?>
          <li class="flex items-baseline justify-between gap-2 py-2"><span><?= e($s['name']) ?> <span class="text-ink-mute"><?= e($s['variant_label']) ?></span></span><span class="whitespace-nowrap font-bold tabular-nums <?= $s['available'] <= 0 ? 'text-alert' : 'text-coffee' ?>"><?= $s['available'] <= 0 ? 'Hết hàng' : 'còn ' . (int)$s['available'] ?></span></li>
        <?php endforeach; ?>
        <?php if (!$low): ?><li class="py-2 text-ink-mute">Mọi quy cách đang bán đều còn trên 10.</li><?php endif; ?>
      </ul>
    </section>

    <section class="a-card">
      <div class="flex items-center justify-between"><h2 class="text-lg">Tình trạng hệ thống</h2><?php if (can('audit.view')): ?><a href="/admin/monitor" class="text-sm font-semibold">Giám sát</a><?php endif; ?></div>
      <?php if (!$issues): ?><p class="mt-2 flex items-center gap-2 text-sm text-ink-soft"><span class="h-2.5 w-2.5 rounded-full bg-tea" aria-hidden="true"></span>Mọi mục đều ổn.</p><?php endif; ?>
      <ul class="mt-2 space-y-2.5 text-sm">
        <?php foreach ($issues as $h): ?>
          <li class="flex items-start gap-2"><span class="mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full <?= $levelCls[$h['level']] ?>" aria-hidden="true"></span><span class="flex-1"><span class="font-semibold"><?= e($h['name']) ?></span><span class="sr-only"> — <?= $h['level'] === 'bad' ? 'lỗi' : 'cần chú ý' ?></span><br><span class="text-ink-mute"><?= e($h['value']) ?></span></span></li>
        <?php endforeach; ?>
      </ul>
      <?php if ($issues && count($health) > count($issues)): ?><p class="mt-3 text-xs text-ink-mute"><?= count($health) - count($issues) ?> mục khác đang ổn.</p><?php endif; ?>
    </section>
  </div>
</div>
