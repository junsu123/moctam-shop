<?php
$tabs = ['' => 'Tất cả', 'pending' => 'Chờ xác nhận', 'review' => 'Cần xem lại', 'confirmed' => 'Đã xác nhận', 'shipping' => 'Đang giao', 'delivered' => 'Đã giao', 'returning' => 'Đang hoàn', 'returned' => 'Đã hoàn', 'cancelled' => 'Đã hủy'];
$cur = $f['status'] ?? '';
?>
<nav class="flex flex-wrap gap-1 text-sm" aria-label="Lọc theo trạng thái">
  <?php foreach ($tabs as $k => $v): $n = $k === '' ? array_sum(array_diff_key($statusCounts, ['review' => 1])) : ($statusCounts[$k] ?? 0); ?>
    <a href="<?= e(url('/admin/orders', array_filter(['status' => $k] + array_intersect_key($f, array_flip(['method', 'q', 'pay']))))) ?>" class="rounded-md px-3 py-1.5 no-underline <?= $cur === $k ? 'bg-tea text-white font-semibold' : 'bg-white text-ink hover:bg-jade-200' ?>"><?= e($v) ?> <span class="<?= $cur === $k ? 'text-jade-200' : 'text-ink-mute' ?>"><?= $n ?></span></a>
  <?php endforeach; ?>
</nav>

<form class="a-card mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-6" method="get">
  <input type="hidden" name="status" value="<?= e($cur) ?>">
  <div class="lg:col-span-2"><label class="label" for="q">Mã đơn, SĐT, mã vận đơn</label><input id="q" name="q" value="<?= e($f['q'] ?? '') ?>" class="field"></div>
  <div><label class="label" for="method">Phương thức</label><select id="method" name="method" class="field"><option value="">Tất cả</option><option value="cod" <?= ($f['method'] ?? '') === 'cod' ? 'selected' : '' ?>>COD</option><option value="vietqr" <?= ($f['method'] ?? '') === 'vietqr' ? 'selected' : '' ?>>VietQR</option></select></div>
  <div><label class="label" for="pay">Thanh toán</label><select id="pay" name="pay" class="field"><option value="">Tất cả</option><?php foreach (\App\Domain\OrderService::PAYMENT_LABELS as $k => $v): ?><option value="<?= $k ?>" <?= ($f['pay'] ?? '') === $k ? 'selected' : '' ?>><?= e($v) ?></option><?php endforeach; ?></select></div>
  <div><label class="label" for="from">Từ ngày</label><input id="from" type="date" name="from" value="<?= e($f['from'] ?? '') ?>" class="field"></div>
  <div><label class="label" for="to">Đến ngày</label><input id="to" type="date" name="to" value="<?= e($f['to'] ?? '') ?>" class="field"></div>
  <div class="flex items-end gap-2 lg:col-span-6"><button class="btn-primary">Lọc</button><a href="/admin/orders" class="btn-ghost">Xóa lọc</a><span class="ml-auto self-center text-sm text-ink-mute"><?= $total ?> đơn</span></div>
</form>

<div class="a-card mt-4 overflow-x-auto p-0">
  <table class="a-table">
    <thead><tr><th>Mã đơn</th><th>Khách</th><th>Tỉnh/thành</th><th class="text-right">Tổng</th><th>Trạng thái</th><th>Thanh toán</th><th>Đặt lúc</th><th>Hạn chờ</th></tr></thead>
    <tbody>
    <?php foreach ($rows as $o): ?>
      <tr>
        <td><a class="font-semibold" href="/admin/orders/<?= $o['id'] ?>"><?= e($o['code']) ?></a>
          <?php if ($o['needs_review']): ?><br><span class="badge bg-alert-light text-alert">Cần xem lại</span><?php endif; ?>
          <?php if ($o['open_disc']): ?><br><span class="badge bg-alert-light text-alert"><?= (int)$o['open_disc'] ?> sai lệch</span><?php endif; ?></td>
        <td><?= e($o['ship_name']) ?><br><span class="text-ink-mute"><?= e($o['ship_phone']) ?></span></td>
        <td><?= e($o['ship_province']) ?></td>
        <td class="text-right font-semibold tabular-nums"><?= money($o['total']) ?></td>
        <td><?= status_badge($o['status']) ?><?php if ($o['tracking_code']): ?><br><span class="text-xs text-ink-mute"><?= e($o['tracking_code']) ?></span><?php endif; ?></td>
        <td><span class="text-xs font-semibold uppercase text-ink-mute"><?= e($o['payment_method']) ?></span><br><?= status_badge($o['payment_status']) ?></td>
        <td class="whitespace-nowrap text-ink-mute"><?= vn_time($o['created_at']) ?></td>
        <td class="whitespace-nowrap <?= $o['status'] === 'pending' && $o['expires_at'] < \App\Core\Clock::nowDb() ? 'font-semibold text-alert' : 'text-ink-mute' ?>"><?= $o['status'] === 'pending' ? vn_time($o['expires_at']) : '' ?></td>
      </tr>
    <?php endforeach; ?>
    <?php if (!$rows): ?><tr><td colspan="8" class="py-8 text-center text-ink-mute">Không có đơn phù hợp bộ lọc.</td></tr><?php endif; ?>
    </tbody>
  </table>
</div>
<?= a_pager($page, $pages, array_intersect_key($f, array_flip(['status', 'method', 'q', 'pay', 'from', 'to']))) ?>
