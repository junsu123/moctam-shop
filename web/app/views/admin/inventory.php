<?php
$out = count(array_filter($rows, fn($r) => $r['available'] <= 0 && $r['status'] === 'active'));
$lowN = count(array_filter($rows, fn($r) => $r['available'] > 0 && $r['available'] <= 10 && $r['status'] === 'active'));
?>
<form class="a-card flex flex-wrap items-end gap-x-4 gap-y-3" method="get">
  <div class="w-full sm:w-64"><label class="label" for="q">Tìm theo mã SKU hoặc tên</label><input id="q" name="q" type="search" value="<?= e($f['q'] ?? '') ?>" class="field"></div>
  <div class="flex flex-wrap gap-x-4 gap-y-2 pb-2.5"><?= a_check('low', 'Chỉ còn ≤ 10', !empty($f['low'])) ?><?= a_check('all', 'Gồm quy cách ngừng bán', !empty($f['all'])) ?></div>
  <button class="btn-primary">Lọc</button>
  <a href="/admin/inventory/movements" class="btn-ghost sm:ml-auto">Lịch sử nhập / xuất kho</a>
</form>

<?php if ($out || $lowN): ?>
  <p class="mt-4 text-sm text-ink-soft"><?php if ($out): ?><span class="font-semibold text-alert"><?= $out ?> quy cách hết hàng</span><?php endif; ?><?= $out && $lowN ? ', ' : '' ?><?php if ($lowN): ?><span class="font-semibold text-coffee"><?= $lowN ?> sắp hết</span><?php endif; ?> — được tô màu trong bảng.</p>
<?php endif; ?>

<div class="a-card mt-4 p-0">
  <table class="a-table">
    <thead><tr><th>Sản phẩm / quy cách</th><th class="hidden text-right sm:table-cell">Tồn thực tế</th><th class="hidden text-right sm:table-cell">Đang giữ cho đơn</th><th class="text-right">Bán được</th><th><span class="sr-only">Thao tác</span></th></tr></thead>
    <tbody>
    <?php foreach ($rows as $r):
      $state = $r['status'] !== 'active' ? '' : ($r['available'] <= 0 ? 'out' : ($r['available'] <= 10 ? 'low' : '')); ?>
      <tr class="<?= $state === 'out' ? 'bg-alert-light/50' : ($state === 'low' ? 'bg-turmeric-light/40' : '') ?>">
        <td><a href="/admin/products/<?= $r['product_id'] ?>" class="font-semibold"><?= e($r['name']) ?></a> <?= $r['status'] !== 'active' ? status_badge($r['status']) : '' ?>
          <br><span class="text-ink-soft"><?= e($r['variant_label']) ?></span> <span class="break-all font-mono text-xs text-ink-mute"><?= e($r['sku_code']) ?></span><span class="block text-xs text-ink-mute sm:hidden">Tồn thực tế <?= (int)$r['on_hand'] ?>, đang giữ <?= (int)$r['reserved'] ?></span></td>
        <td class="hidden text-right tabular-nums sm:table-cell"><?= (int)$r['on_hand'] ?></td>
        <td class="hidden text-right tabular-nums text-ink-mute sm:table-cell"><?= (int)$r['reserved'] ?></td>
        <td class="text-right tabular-nums">
          <span class="text-lg font-bold <?= $state === 'out' ? 'text-alert' : ($state === 'low' ? 'text-coffee' : '') ?>"><?= (int)$r['available'] ?></span>
          <?php if ($state === 'out'): ?><span class="block text-xs font-semibold text-alert">Hết hàng</span><?php elseif ($state === 'low'): ?><span class="block text-xs font-semibold text-coffee">Sắp hết</span><?php endif; ?>
        </td>
        <td class="w-0 whitespace-nowrap text-right">
          <details class="relative inline-block text-left" data-inline-form>
            <summary class="btn-ghost cursor-pointer list-none px-3 py-1.5 text-sm [&::-webkit-details-marker]:hidden" aria-label="Nhập kho hoặc điều chỉnh <?= e($r['sku_code']) ?>"><span class="sm:hidden">Điều chỉnh</span><span class="hidden sm:inline">Nhập / điều chỉnh</span></summary>
            <form method="post" action="/admin/inventory/<?= $r['id'] ?>/adjust" class="absolute right-0 z-10 mt-2 w-72 space-y-3 rounded-xl border border-ink/15 bg-white p-4 text-left shadow-lg">
              <?= csrf_field() ?>
              <fieldset><legend class="label">Loại</legend>
                <div class="flex gap-4 text-sm">
                  <label class="inline-flex items-center gap-1.5"><input type="radio" name="type" value="receive" class="accent-tea" checked> Nhập kho (+)</label>
                  <label class="inline-flex items-center gap-1.5"><input type="radio" name="type" value="adjust" class="accent-tea"> Điều chỉnh (±)</label>
                </div>
              </fieldset>
              <div><label class="label" for="d<?= $r['id'] ?>">Số lượng</label><input id="d<?= $r['id'] ?>" name="delta" type="number" inputmode="numeric" class="field py-2" placeholder="VD: 50 hoặc -2" required></div>
              <div><label class="label" for="r<?= $r['id'] ?>">Lý do</label><input id="r<?= $r['id'] ?>" name="reason" class="field py-2" placeholder="VD: nhập mẻ 25/11, kiểm kê lệch" required></div>
              <div class="flex items-center justify-between gap-2">
                <a class="text-sm" href="/admin/inventory/movements?sku=<?= e($r['sku_code']) ?>">Xem lịch sử</a>
                <button class="btn-primary px-4 py-2 text-sm">Lưu</button>
              </div>
            </form>
          </details>
        </td>
      </tr>
    <?php endforeach; ?>
    <?php if (!$rows): ?><tr><td colspan="5" class="py-6 text-center text-ink-mute">Không có quy cách phù hợp bộ lọc.</td></tr><?php endif; ?>
    </tbody>
  </table>
</div>
