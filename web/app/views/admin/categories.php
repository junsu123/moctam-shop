<div class="grid gap-6 xl:grid-cols-[1fr_380px]">
  <div class="space-y-3">
    <?php foreach ($rows as $c): ?>
      <details class="a-card">
        <summary class="flex cursor-pointer items-center gap-3"><span class="font-semibold"><?= e($c['name']) ?></span> <span class="text-sm text-ink-mute"><?= (int)$c['n'] ?> sản phẩm, /danh-muc/<?= e($c['slug']) ?></span> <?= $c['is_active'] ? '' : status_badge('discontinued', 'Ẩn') ?></summary>
        <form method="post" action="/admin/categories/save" class="mt-4 grid gap-3 sm:grid-cols-2"><?= csrf_field() ?>
          <input type="hidden" name="id" value="<?= $c['id'] ?>">
          <?= a_field('name', 'Tên', $c['name'], []) ?>
          <?= a_field('sort_order', 'Thứ tự', $c['sort_order'], [], ['type' => 'number']) ?>
          <?= a_field('description', 'Mô tả', $c['description'], [], ['wrap' => 'sm:col-span-2']) ?>
          <?= a_field('repurchase_days', 'Chu kỳ mua lại tham khảo (ngày)', $c['repurchase_days'], [], ['type' => 'number', 'hint' => 'Dịch vụ Python dùng làm giá trị ban đầu khi chưa đủ dữ liệu đơn.']) ?>
          <div class="flex items-end"><?= a_check('is_active', 'Hiển thị', (bool)$c['is_active']) ?></div>
          <button class="btn-ghost sm:col-span-2">Lưu danh mục</button>
        </form>
      </details>
    <?php endforeach; ?>
  </div>
  <form method="post" action="/admin/categories/save" class="a-card h-fit space-y-3"><?= csrf_field() ?>
    <h2 class="text-lg">Thêm danh mục</h2>
    <?= a_field('name', 'Tên', $old['name'] ?? '', $errors) ?>
    <?= a_field('description', 'Mô tả', $old['description'] ?? '', $errors) ?>
    <?= a_field('repurchase_days', 'Chu kỳ mua lại (ngày)', $old['repurchase_days'] ?? '', $errors, ['type' => 'number']) ?>
    <?= a_field('sort_order', 'Thứ tự', $old['sort_order'] ?? '0', $errors, ['type' => 'number']) ?>
    <input type="hidden" name="is_active" value="1">
    <button class="btn-primary w-full">Thêm danh mục</button>
  </form>
</div>
