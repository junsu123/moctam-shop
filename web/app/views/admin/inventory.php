<form class="flex flex-wrap items-end gap-3" method="get">
  <div><label class="label" for="q">Tìm SKU / tên</label><input id="q" name="q" value="<?= e($f['q'] ?? '') ?>" class="field"></div>
  <?= a_check('low', 'Chỉ SKU khả dụng ≤ 10', !empty($f['low'])) ?>
  <?= a_check('all', 'Gồm SKU ngừng bán', !empty($f['all'])) ?>
  <button class="btn-primary">Lọc</button>
  <a href="/admin/inventory/movements" class="btn-ghost ml-auto">Tra biến động kho</a>
</form>

<div class="a-card mt-4 overflow-x-auto p-0">
  <table class="a-table">
    <thead><tr><th>Sản phẩm / SKU</th><th class="text-right">Tồn thực tế</th><th class="text-right">Đang giữ</th><th class="text-right">Khả dụng</th><th>Nhập kho / điều chỉnh (bắt buộc lý do)</th></tr></thead>
    <tbody>
    <?php foreach ($rows as $r): ?>
      <tr>
        <td><a href="/admin/products/<?= $r['product_id'] ?>" class="font-semibold"><?= e($r['name']) ?></a><br><span class="font-mono text-xs"><?= e($r['sku_code']) ?></span> <span class="text-ink-mute"><?= e($r['variant_label']) ?></span> <?= $r['status'] !== 'active' ? status_badge($r['status']) : '' ?>
          <br><a class="text-xs" href="/admin/inventory/movements?sku=<?= e($r['sku_code']) ?>">Lịch sử</a></td>
        <td class="text-right tabular-nums"><?= (int)$r['on_hand'] ?></td>
        <td class="text-right tabular-nums text-ink-mute"><?= (int)$r['reserved'] ?></td>
        <td class="text-right text-lg font-bold tabular-nums <?= $r['available'] <= 0 ? 'text-alert' : ($r['available'] <= 10 ? 'text-coffee' : '') ?>"><?= (int)$r['available'] ?></td>
        <td>
          <form method="post" action="/admin/inventory/<?= $r['id'] ?>/adjust" class="flex flex-wrap items-center gap-2">
            <?= csrf_field() ?>
            <label class="sr-only" for="t<?= $r['id'] ?>">Loại</label>
            <select id="t<?= $r['id'] ?>" name="type" class="field w-auto py-1.5 text-sm"><option value="receive">Nhập kho</option><option value="adjust">Điều chỉnh (±)</option></select>
            <label class="sr-only" for="d<?= $r['id'] ?>">Số lượng</label>
            <input id="d<?= $r['id'] ?>" name="delta" type="number" class="field w-24 py-1.5 text-sm" placeholder="±SL" required>
            <label class="sr-only" for="r<?= $r['id'] ?>">Lý do</label>
            <input id="r<?= $r['id'] ?>" name="reason" class="field w-48 py-1.5 text-sm" placeholder="Lý do (VD: nhập mẻ 25/11)" required>
            <button class="btn-ghost px-3 py-1.5 text-sm">Lưu</button>
          </form>
        </td>
      </tr>
    <?php endforeach; ?>
    <?php if (!$rows): ?><tr><td colspan="5" class="py-6 text-center text-ink-mute">Không có SKU phù hợp.</td></tr><?php endif; ?>
    </tbody>
  </table>
</div>
