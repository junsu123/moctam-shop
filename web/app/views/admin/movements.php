<?php $mvLabel = ['reserve' => 'Giữ tồn', 'release' => 'Giải phóng giữ', 'ship' => 'Xuất kho', 'return_restock' => 'Nhập lại (đạt)', 'return_reject' => 'Không đạt kiểm', 'adjust' => 'Điều chỉnh', 'receive' => 'Nhập kho']; ?>
<form class="flex flex-wrap items-end gap-3" method="get">
  <div><label class="label" for="sku">Mã SKU</label><input id="sku" name="sku" value="<?= e($f['sku'] ?? '') ?>" class="field"></div>
  <div><label class="label" for="order">Mã đơn</label><input id="order" name="order" value="<?= e($f['order'] ?? '') ?>" class="field"></div>
  <div><label class="label" for="type">Loại</label><select id="type" name="type" class="field"><option value="">Tất cả</option><?php foreach ($mvLabel as $k => $v): ?><option value="<?= $k ?>" <?= ($f['type'] ?? '') === $k ? 'selected' : '' ?>><?= $v ?></option><?php endforeach; ?></select></div>
  <button class="btn-primary">Tra cứu</button>
</form>
<div class="a-card mt-4 overflow-x-auto p-0">
  <table class="a-table">
    <thead><tr><th>Thời điểm</th><th>SKU</th><th>Loại</th><th class="text-right">Thực tế</th><th class="text-right">Giữ</th><th class="text-right">Sau (thực tế/giữ)</th><th>Đơn</th><th>Lý do</th><th>Người</th></tr></thead>
    <tbody>
    <?php foreach ($rows as $m): ?>
      <tr>
        <td class="whitespace-nowrap"><?= vn_time($m['created_at'], 'd/m/Y H:i:s') ?></td>
        <td class="font-mono text-xs"><?= e($m['sku_code']) ?></td>
        <td><?= e($mvLabel[$m['type']] ?? $m['type']) ?></td>
        <td class="text-right tabular-nums <?= $m['on_hand_delta'] < 0 ? 'text-alert' : ($m['on_hand_delta'] > 0 ? 'text-tea' : 'text-ink-mute') ?>"><?= sprintf('%+d', $m['on_hand_delta']) ?></td>
        <td class="text-right tabular-nums text-ink-mute"><?= sprintf('%+d', $m['reserved_delta']) ?></td>
        <td class="text-right tabular-nums"><?= (int)$m['on_hand_after'] ?> / <?= (int)$m['reserved_after'] ?></td>
        <td><?php if ($m['order_code']): ?><a href="/admin/orders/<?= $m['oid'] ?>"><?= e($m['order_code']) ?></a><?php endif; ?></td>
        <td class="text-xs"><?= e($m['reason']) ?></td>
        <td class="text-xs"><?= e($m['full_name'] ?? ($m['order_code'] ? 'hệ thống' : '')) ?></td>
      </tr>
    <?php endforeach; ?>
    <?php if (!$rows): ?><tr><td colspan="9" class="py-6 text-center text-ink-mute">Không có biến động.</td></tr><?php endif; ?>
    </tbody>
  </table>
</div>
<?= a_pager($page, $pages, array_intersect_key($f, array_flip(['sku', 'order', 'type']))) ?>
