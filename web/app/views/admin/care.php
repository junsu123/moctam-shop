<div class="flex flex-wrap items-center gap-2">
  <nav class="flex gap-1 text-sm">
    <?php foreach (['pending' => 'Chờ xử lý', 'contacted' => 'Đã liên hệ', 'skipped' => 'Bỏ qua'] as $k => $v): ?>
      <a href="?status=<?= $k ?>&consent=<?= $consentOnly ? 1 : 0 ?>" class="rounded-md px-3 py-1.5 no-underline <?= $st === $k ? 'bg-tea text-white font-semibold' : 'bg-white text-ink' ?>"><?= $v ?></a>
    <?php endforeach; ?>
  </nav>
  <a href="?status=<?= $st ?>&consent=<?= $consentOnly ? 0 : 1 ?>" class="text-sm"><?= $consentOnly ? 'Hiện cả khách chưa đồng ý (chỉ để xem)' : 'Chỉ khách đã đồng ý' ?></a>
  <a href="/admin/care/export" class="btn-ghost ml-auto">Xuất CSV (khách đã đồng ý)</a>
</div>
<p class="mt-3 max-w-3xl text-sm text-ink-soft">Dịch vụ Python ước tính thời điểm mua lại theo nhóm hàng và đơn đã giao. Đây là đề xuất — nhân viên quyết định cách xử lý. Chỉ liên hệ chào hàng với khách đã đồng ý nhận tiếp thị khi đặt hàng.<?= $hidden ? " Đang ẩn $hidden khách chưa đồng ý." : '' ?></p>
<div class="a-card mt-4 overflow-x-auto p-0">
  <table class="a-table">
    <thead><tr><th>Khách</th><th>Nhóm hàng</th><th>Lần mua cuối</th><th>Đến kỳ</th><th class="text-right">Điểm</th><th>Lý do</th><th>Đồng ý</th><th></th></tr></thead>
    <tbody>
    <?php foreach ($rows as $r): ?>
      <tr>
        <td class="font-semibold"><?= e($r['full_name']) ?><br><span class="font-normal <?= $r['marketing_consent'] ? '' : 'text-ink-mute' ?>"><?= $r['marketing_consent'] ? e($r['phone']) : e(\App\Core\Text::maskPhone($r['phone'])) ?></span><br><span class="text-xs font-normal text-ink-mute"><?= (int)$r['delivered_orders'] ?> đơn đã giao</span></td>
        <td><?= e($r['cat_name'] ?? '—') ?></td>
        <td class="whitespace-nowrap"><?= $r['last_order_at'] ? vn_time($r['last_order_at'], 'd/m/Y') : '' ?></td>
        <td class="whitespace-nowrap <?= $r['due_date'] <= date('Y-m-d') ? 'font-semibold text-coffee' : '' ?>"><?= e(date('d/m/Y', strtotime($r['due_date']))) ?></td>
        <td class="text-right tabular-nums"><?= $r['score'] !== null ? number_format((float)$r['score'], 2) : '' ?></td>
        <td class="max-w-xs text-xs text-ink-soft"><?= e($r['reason']) ?></td>
        <td><?= $r['marketing_consent'] ? status_badge('approved', 'Có') : status_badge('rejected', 'Không') ?></td>
        <td class="whitespace-nowrap">
          <?php if ($st === 'pending'): ?>
            <?php if ($r['marketing_consent']): ?><form method="post" action="/admin/care/<?= $r['id'] ?>/status" class="inline"><?= csrf_field() ?><input type="hidden" name="to" value="contacted"><button class="btn-primary px-3 py-1 text-xs">Đã liên hệ</button></form><?php endif; ?>
            <form method="post" action="/admin/care/<?= $r['id'] ?>/status" class="inline"><?= csrf_field() ?><input type="hidden" name="to" value="skipped"><button class="btn-ghost px-3 py-1 text-xs">Bỏ qua</button></form>
          <?php endif; ?>
        </td>
      </tr>
    <?php endforeach; ?>
    <?php if (!$rows): ?><tr><td colspan="8" class="py-6 text-center text-ink-mute">Chưa có đề xuất. Danh sách được dịch vụ Python gửi lên khi chạy tác vụ chăm sóc khách hàng.</td></tr><?php endif; ?>
    </tbody>
  </table>
</div>
