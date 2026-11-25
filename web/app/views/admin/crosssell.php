<p class="max-w-3xl text-sm text-ink-soft">Gợi ý do dịch vụ Python đề xuất từ các đơn đã giao (mua cùng nhau) ở trạng thái chờ duyệt. Chỉ gợi ý đã duyệt mới hiện ở trang sản phẩm và trong chat.</p>
<div class="a-card mt-4 overflow-x-auto p-0">
  <table class="a-table">
    <thead><tr><th>Khi xem</th><th>Gợi ý mua kèm</th><th>Nguồn</th><th class="text-right">Điểm</th><th>Lý do</th><th>Trạng thái</th><th></th></tr></thead>
    <tbody>
    <?php foreach ($rows as $r): ?>
      <tr>
        <td><a href="/san-pham/<?= e($r['a_slug']) ?>" target="_blank" rel="noopener"><?= e($r['a_name']) ?></a></td>
        <td class="font-semibold"><?= e($r['b_name']) ?></td>
        <td><?= $r['source'] === 'ai' ? 'AI' : 'Nhân viên' ?></td>
        <td class="text-right tabular-nums"><?= $r['score'] !== null ? number_format((float)$r['score'], 2) : '' ?></td>
        <td class="max-w-xs text-xs text-ink-soft"><?= e($r['reason']) ?></td>
        <td><?= status_badge($r['status'], $r['status'] === 'pending' ? 'Chờ duyệt' : null) ?></td>
        <td class="whitespace-nowrap">
          <?php if ($r['status'] !== 'approved'): ?><form method="post" action="/admin/crosssell/<?= $r['id'] ?>/review" class="inline"><?= csrf_field() ?><input type="hidden" name="decision" value="approve"><button class="btn-primary px-3 py-1 text-xs">Duyệt</button></form><?php endif; ?>
          <?php if ($r['status'] !== 'rejected'): ?><form method="post" action="/admin/crosssell/<?= $r['id'] ?>/review" class="inline"><?= csrf_field() ?><input type="hidden" name="decision" value="reject"><button class="btn-ghost px-3 py-1 text-xs">Từ chối</button></form><?php endif; ?>
        </td>
      </tr>
    <?php endforeach; ?>
    <?php if (!$rows): ?><tr><td colspan="7" class="py-6 text-center text-ink-mute">Chưa có gợi ý.</td></tr><?php endif; ?>
    </tbody>
  </table>
</div>
