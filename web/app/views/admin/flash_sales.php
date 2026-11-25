<div class="flex justify-end"><a href="/admin/flash-sales/new" class="btn-primary">Tạo Flash Sale</a></div>
<div class="a-card mt-4 overflow-x-auto p-0">
  <table class="a-table">
    <thead><tr><th>Chương trình</th><th>Bắt đầu</th><th>Kết thúc</th><th class="text-right">Số SKU</th><th>Dùng cùng voucher</th><th>Trạng thái</th></tr></thead>
    <tbody>
    <?php $now = \App\Core\Clock::nowDb(); foreach ($rows as $f):
      $state = !$f['is_active'] ? ['discontinued', 'Tắt'] : ($now < $f['starts_at'] ? ['pending_review', 'Sắp diễn ra'] : ($now >= $f['ends_at'] ? ['cancelled', 'Đã kết thúc'] : ['active', 'Đang chạy'])); ?>
      <tr>
        <td><a href="/admin/flash-sales/<?= $f['id'] ?>" class="font-semibold"><?= e($f['name']) ?></a></td>
        <td class="whitespace-nowrap"><?= vn_time($f['starts_at']) ?></td>
        <td class="whitespace-nowrap"><?= vn_time($f['ends_at']) ?></td>
        <td class="text-right"><?= (int)$f['n'] ?></td>
        <td><?= $f['allow_voucher'] ? 'Có' : 'Không' ?></td>
        <td><?= status_badge($state[0], $state[1]) ?></td>
      </tr>
    <?php endforeach; ?>
    <?php if (!$rows): ?><tr><td colspan="6" class="py-6 text-center text-ink-mute">Chưa có chương trình.</td></tr><?php endif; ?>
    </tbody>
  </table>
</div>
