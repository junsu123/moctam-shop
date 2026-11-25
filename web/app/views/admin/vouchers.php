<div class="flex justify-end"><a href="/admin/vouchers/new" class="btn-primary">Tạo voucher</a></div>
<div class="a-card mt-4 overflow-x-auto p-0">
  <table class="a-table">
    <thead><tr><th>Mã</th><th class="text-right">Giảm</th><th class="text-right">Đơn tối thiểu</th><th>Phạm vi</th><th>Thời gian</th><th class="text-right">Đã dùng / giữ / giới hạn</th><th>Trạng thái</th></tr></thead>
    <tbody>
    <?php $now = \App\Core\Clock::nowDb(); foreach ($rows as $v):
      $state = !$v['is_active'] ? ['discontinued', 'Tắt'] : ($now < $v['starts_at'] ? ['pending_review', 'Sắp diễn ra'] : ($now >= $v['ends_at'] ? ['cancelled', 'Hết hạn'] : ['active', 'Đang chạy'])); ?>
      <tr data-href="/admin/vouchers/<?= (int)$v['id'] ?>">
        <td><a href="/admin/vouchers/<?= $v['id'] ?>" class="font-mono font-bold"><?= e($v['code']) ?></a><br><span class="text-xs text-ink-mute"><?= e($v['description']) ?></span></td>
        <td class="text-right tabular-nums"><?= money($v['amount']) ?></td>
        <td class="text-right tabular-nums"><?= money($v['min_subtotal']) ?></td>
        <td><?= ['all' => 'Toàn bộ', 'category' => 'Theo danh mục', 'product' => 'Theo sản phẩm'][$v['scope_type']] ?></td>
        <td class="whitespace-nowrap text-xs"><?= vn_time($v['starts_at']) ?><br><?= vn_time($v['ends_at']) ?></td>
        <td class="text-right tabular-nums"><?= (int)$v['used_count'] ?> / <?= (int)$v['reserved_count'] ?> / <?= $v['usage_limit'] ?? '∞' ?></td>
        <td><?= status_badge($state[0], $state[1]) ?></td>
      </tr>
    <?php endforeach; ?>
    </tbody>
  </table>
</div>
