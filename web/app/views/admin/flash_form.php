<?php
$val = fn($k, $d = '') => $old[$k] ?? ($fs[$k] ?? $d);
$skuOpts = '';
foreach ($skus as $s) $skuOpts .= '<option value="' . $s['id'] . '">' . e($s['name'] . ' — ' . $s['variant_label'] . ' (' . $s['sku_code'] . ', ' . money($s['price']) . ')') . '</option>';
$row = function ($skuId, $price) use ($skus) {
    $o = '<option value="">— Chọn SKU —</option>';
    foreach ($skus as $s) $o .= '<option value="' . $s['id'] . '"' . ((int)$s['id'] === (int)$skuId ? ' selected' : '') . '>' . e($s['name'] . ' — ' . $s['variant_label'] . ' (' . $s['sku_code'] . ', ' . money($s['price']) . ')') . '</option>';
    return '<div class="flex gap-2" data-fs-row><label class="sr-only">SKU</label><select name="item_sku[]" class="field">' . $o . '</select><label class="sr-only">Giá Flash Sale</label><input name="item_price[]" type="number" min="1" value="' . e($price) . '" class="field w-36" placeholder="Giá FS (₫)"><button type="button" class="px-2 text-alert" data-fs-remove aria-label="Bỏ dòng">✕</button></div>';
};
?>
<a href="/admin/flash-sales" class="text-sm">← Danh sách Flash Sale</a>
<form method="post" action="/admin/flash-sales/save" class="a-card mt-3 max-w-4xl space-y-4"><?= csrf_field() ?>
  <input type="hidden" name="id" value="<?= (int)($fs['id'] ?? 0) ?>">
  <div class="grid gap-4 sm:grid-cols-3">
    <?= a_field('name', 'Tên chương trình', $val('name'), $errors, ['wrap' => 'sm:col-span-3']) ?>
    <?= a_field('starts_at', 'Bắt đầu', \App\Core\Clock::toLocalInput($fs['starts_at'] ?? null) ?: ($old['starts_at'] ?? ''), $errors, ['type' => 'datetime-local']) ?>
    <?= a_field('ends_at', 'Kết thúc', \App\Core\Clock::toLocalInput($fs['ends_at'] ?? null) ?: ($old['ends_at'] ?? ''), $errors, ['type' => 'datetime-local']) ?>
    <div class="flex flex-col justify-end gap-2"><?= a_check('allow_voucher', 'Cho tính vào voucher', (bool)$val('allow_voucher', 0)) ?><?= a_check('is_active', 'Đang bật', (bool)$val('is_active', 1)) ?></div>
  </div>
  <fieldset>
    <legend class="label">SKU và giá Flash Sale</legend>
    <p class="mb-2 text-xs text-ink-mute">Giá phải thấp hơn giá niêm yết. Mỗi SKU chỉ thuộc một chương trình đang bật tại một thời điểm — hệ thống từ chối nếu thời gian chồng lấn.</p>
    <div class="space-y-2" data-fs-rows>
      <?php foreach ($items as $it): ?><?= $row($it['sku_id'], $it['sale_price']) ?><?php endforeach; ?>
      <?php if (!$items): ?><?= $row(null, '') ?><?php endif; ?>
    </div>
    <template data-fs-template><?= $row(null, '') ?></template>
    <button type="button" class="btn-ghost mt-2 px-3 py-1.5 text-sm" data-fs-add>Thêm SKU</button>
    <?php if (!empty($errors['items'])): ?><p class="err-msg"><?= e($errors['items']) ?></p><?php endif; ?>
  </fieldset>
  <button class="btn-primary">Lưu Flash Sale</button>
</form>
