<?php
$val = fn($k, $d = '') => $old[$k] ?? ($v[$k] ?? $d);
$scopeIds = array_map('intval', $old ? array_merge((array)($old['scope_cat'] ?? []), (array)($old['scope_prod'] ?? [])) : json_dec($v['scope_ids'] ?? '[]'));
?>
<a href="/admin/vouchers" class="text-sm">← Danh sách voucher</a>
<div class="mt-3 grid gap-6 xl:grid-cols-[1fr_380px]">
  <form method="post" action="/admin/vouchers/save" class="a-card grid gap-4 sm:grid-cols-2"><?= csrf_field() ?>
    <input type="hidden" name="id" value="<?= (int)($v['id'] ?? 0) ?>">
    <?= a_field('code', 'Mã (chữ in hoa, số)', $val('code'), $errors, ['class' => 'uppercase font-mono']) ?>
    <?= a_field('description', 'Mô tả hiển thị', $val('description'), $errors) ?>
    <?= a_field('amount', 'Số tiền giảm cố định (₫)', $val('amount'), $errors, ['type' => 'number']) ?>
    <?= a_field('min_subtotal', 'Đơn tối thiểu (₫)', $val('min_subtotal', 0), $errors, ['type' => 'number', 'hint' => 'Tính trên tiền hàng ĐỦ ĐIỀU KIỆN sau Flash Sale, trước phí giao.']) ?>
    <?= a_field('starts_at', 'Bắt đầu', \App\Core\Clock::toLocalInput($v['starts_at'] ?? null) ?: ($old['starts_at'] ?? ''), $errors, ['type' => 'datetime-local']) ?>
    <?= a_field('ends_at', 'Kết thúc', \App\Core\Clock::toLocalInput($v['ends_at'] ?? null) ?: ($old['ends_at'] ?? ''), $errors, ['type' => 'datetime-local']) ?>
    <?= a_field('usage_limit', 'Giới hạn lượt dùng (trống = không giới hạn)', $val('usage_limit'), $errors, ['type' => 'number']) ?>
    <?= a_field('scope_type', 'Phạm vi áp dụng', $val('scope_type', 'all'), $errors, ['type' => 'select', 'options' => ['all' => 'Toàn bộ sản phẩm', 'category' => 'Theo danh mục', 'product' => 'Theo sản phẩm'], 'attrs' => 'data-scope-type']) ?>
    <fieldset class="sm:col-span-2" data-scope-box="category"><legend class="label">Danh mục áp dụng</legend><div class="flex flex-wrap gap-3">
      <?php foreach ($cats as $c): ?><label class="text-sm"><input type="checkbox" name="scope_cat[]" value="<?= $c['id'] ?>" class="accent-tea" <?= in_array((int)$c['id'], $scopeIds, true) ? 'checked' : '' ?>> <?= e($c['name']) ?></label><?php endforeach; ?>
    </div></fieldset>
    <fieldset class="sm:col-span-2" data-scope-box="product"><legend class="label">Sản phẩm áp dụng</legend><div class="grid max-h-56 gap-1 overflow-y-auto sm:grid-cols-2">
      <?php foreach ($products as $p): ?><label class="text-sm"><input type="checkbox" name="scope_prod[]" value="<?= $p['id'] ?>" class="accent-tea" <?= in_array((int)$p['id'], $scopeIds, true) ? 'checked' : '' ?>> <?= e($p['name']) ?></label><?php endforeach; ?>
    </div></fieldset>
    <?php if (!empty($errors['scope_ids'])): ?><p class="err-msg sm:col-span-2"><?= e($errors['scope_ids']) ?></p><?php endif; ?>
    <div class="sm:col-span-2"><?= a_check('is_active', 'Đang bật', (bool)$val('is_active', 1)) ?></div>
    <p class="text-xs text-ink-mute sm:col-span-2">Mỗi đơn dùng một voucher. Số tiền giảm tối đa bằng tiền hàng đủ điều kiện. Lượt dùng được giữ khi đặt đơn, chuyển sang "đã dùng" khi bàn giao, và trả lại khi đơn hủy trước bàn giao.</p>
    <button class="btn-primary sm:col-span-2">Lưu voucher</button>
  </form>
  <?php if ($v): ?>
  <section class="a-card h-fit">
    <h2 class="text-lg">Lượt sử dụng</h2>
    <p class="text-sm text-ink-mute">Đã dùng <?= (int)$v['used_count'] ?>, đang giữ <?= (int)$v['reserved_count'] ?>.</p>
    <ul class="mt-3 space-y-1 text-sm">
      <?php foreach ($usages as $u): ?><li class="flex justify-between"><a href="/admin/orders/<?= $u['order_id'] ?>"><?= e($u['code']) ?></a><span><?= money($u['amount']) ?> — <?= ['reserved' => 'đang giữ', 'used' => 'đã dùng', 'released' => 'đã trả lượt'][$u['status']] ?></span></li><?php endforeach; ?>
    </ul>
  </section>
  <?php endif; ?>
</div>
