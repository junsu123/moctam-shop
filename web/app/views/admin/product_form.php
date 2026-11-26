<?php
$v = fn(string $k, $d = '') => $old[$k] ?? ($p[$k] ?? $d);
$catOpts = ['' => '— Chọn —'] + array_column($cats, 'name', 'id');
?>
<a href="/admin/products" class="text-sm">← Danh sách sản phẩm</a>
<div class="mt-3 grid gap-6 xl:grid-cols-[1fr_420px]">
  <form method="post" action="/admin/products/save" class="a-card space-y-4">
    <?= csrf_field() ?>
    <input type="hidden" name="id" value="<?= (int)($p['id'] ?? 0) ?>">
    <div class="grid gap-4 sm:grid-cols-2">
      <?= a_field('name', 'Tên sản phẩm', $v('name'), $errors, ['required' => true, 'wrap' => 'sm:col-span-2']) ?>
      <?= a_field('category_id', 'Danh mục', $v('category_id'), $errors, ['type' => 'select', 'options' => $catOpts]) ?>
      <?= a_field('status', 'Trạng thái', $v('status', 'draft'), $errors, ['type' => 'select', 'options' => ['draft' => 'Nháp (chưa hiện)', 'active' => 'Đang bán', 'discontinued' => 'Ngừng bán']]) ?>
      <?php if (!$p): ?><?= a_field('slug', 'Đường dẫn (để trống sẽ tự tạo)', $v('slug'), $errors, ['hint' => 'Cố định sau khi tạo để không gãy liên kết.']) ?><?php endif; ?>
      <?= a_field('keywords', 'Từ khóa tìm kiếm', $v('keywords'), $errors, ['hint' => 'Cách nhau bởi dấu phẩy. VD: tra gung, ginger tea']) ?>
    </div>
    <?= a_field('short_desc', 'Mô tả ngắn', $v('short_desc'), $errors, ['type' => 'textarea', 'rows' => 2]) ?>
    <?= a_field('description', 'Mô tả chi tiết (HTML cơ bản: p, h2, ul, strong, a, img)', $v('description'), $errors, ['type' => 'textarea', 'rows' => 6, 'hint' => 'Mã script và thuộc tính sự kiện sẽ bị lọc bỏ khi lưu.']) ?>
    <div class="rounded-lg bg-turmeric-light/60 p-4">
      <p class="text-sm font-semibold">Thông tin nhãn — chat tư vấn trích nguyên văn mục này</p>
      <p class="text-xs text-ink-soft">Nhập đúng theo nhãn/tài liệu đã duyệt. Thay đổi các mục này sẽ tăng phiên bản thông tin; bản nháp AI dựa trên phiên bản cũ sẽ bị từ chối.</p>
      <div class="mt-3 grid gap-4 sm:grid-cols-2">
        <?= a_field('ingredients', 'Thành phần', $v('ingredients'), $errors, ['type' => 'textarea', 'rows' => 3]) ?>
        <?= a_field('usage_guide', 'Cách dùng', $v('usage_guide'), $errors, ['type' => 'textarea', 'rows' => 3]) ?>
        <?= a_field('storage_guide', 'Bảo quản', $v('storage_guide'), $errors, ['type' => 'textarea', 'rows' => 3]) ?>
        <?= a_field('allergens', 'Thông tin dị ứng', $v('allergens'), $errors, ['type' => 'textarea', 'rows' => 3]) ?>
      </div>
    </div>
    <?= a_check('is_featured', 'Hiện ở mục "Xưởng gợi ý" trên trang chủ', (bool)$v('is_featured', 0)) ?>
    <div class="flex flex-wrap items-center gap-3 border-t border-ink/10 pt-4">
      <button class="btn-primary"><?= $p ? 'Lưu sản phẩm' : 'Tạo sản phẩm' ?></button>
      <?php if ($p && $p['status'] === 'active'): ?><a href="<?= e(page_url($p['slug'])) ?>" target="_blank" rel="noopener" class="text-sm">Xem trên cửa hàng</a><?php endif; ?>
      <?php if ($p): ?><span class="ml-auto text-xs text-ink-mute">Phiên bản thông tin nhãn: v<?= (int)$p['info_version'] ?></span><?php endif; ?>
    </div>
  </form>

  <?php if ($p): ?>
  <div class="space-y-6">
    <section class="a-card">
      <h2 class="text-lg">Quy cách bán (SKU)</h2>
      <p class="text-xs text-ink-mute">Mỗi quy cách có mã, giá và tồn kho riêng. Đổi giá được ghi nhật ký.</p>
      <?php foreach ($skus as $s): ?>
        <details class="mt-3 rounded-lg border border-ink/10 p-3">
          <summary class="flex cursor-pointer flex-wrap items-center gap-2 text-sm"><span class="font-mono font-semibold"><?= e($s['sku_code']) ?></span> <?= e($s['variant_label']) ?> <span class="ml-auto font-bold tabular-nums"><?= money($s['price']) ?></span> <?= $s['status'] !== 'active' ? status_badge($s['status']) : '' ?></summary>
          <form method="post" action="/admin/products/<?= $p['id'] ?>/sku" class="mt-3 grid grid-cols-2 gap-3"><?= csrf_field() ?>
            <input type="hidden" name="sku_id" value="<?= $s['id'] ?>">
            <?= a_field('sku_code', 'Mã SKU', $s['sku_code'], [], []) ?>
            <?= a_field('variant_label', 'Quy cách', $s['variant_label'], [], []) ?>
            <?= a_field('price', 'Giá (₫)', $s['price'], [], ['type' => 'number']) ?>
            <?= a_field('net_weight_g', 'Khối lượng (g)', $s['net_weight_g'], [], ['type' => 'number']) ?>
            <?= a_field('sort_order', 'Thứ tự', $s['sort_order'], [], ['type' => 'number']) ?>
            <?= a_field('status', 'Trạng thái', $s['status'], [], ['type' => 'select', 'options' => ['active' => 'Đang bán', 'discontinued' => 'Ngừng bán']]) ?>
            <p class="col-span-2 text-xs text-ink-mute">Tồn: <?= (int)$s['on_hand'] ?> thực tế, <?= (int)$s['reserved'] ?> đang giữ — điều chỉnh ở trang <a href="/admin/inventory?q=<?= e($s['sku_code']) ?>">Tồn kho</a>.</p>
            <button class="btn-ghost col-span-2">Lưu quy cách</button>
          </form>
        </details>
      <?php endforeach; ?>
      <form method="post" action="/admin/products/<?= $p['id'] ?>/sku" class="mt-4 grid grid-cols-2 gap-3 rounded-lg bg-jade-50 p-3"><?= csrf_field() ?>
        <p class="col-span-2 text-sm font-semibold">Thêm quy cách</p>
        <?= a_field('sku_code', 'Mã SKU', $old['sku_code'] ?? '', $errors) ?>
        <?= a_field('variant_label', 'Quy cách', $old['variant_label'] ?? '', $errors, ['attrs' => 'placeholder="Hộp 20 túi x 2g"']) ?>
        <?= a_field('price', 'Giá (₫)', $old['price'] ?? '', $errors, ['type' => 'number']) ?>
        <?= a_field('net_weight_g', 'Khối lượng (g)', $old['net_weight_g'] ?? '', $errors, ['type' => 'number']) ?>
        <button class="btn-primary col-span-2">Thêm SKU</button>
      </form>
    </section>

    <section class="a-card">
      <h2 class="text-lg">Ảnh</h2>
      <div class="mt-3 grid grid-cols-4 gap-2">
        <?php foreach ($images as $img): ?>
          <form method="post" action="/admin/products/<?= $p['id'] ?>/image-delete" class="relative" data-confirm="Xóa ảnh này?"><?= csrf_field() ?>
            <input type="hidden" name="image_id" value="<?= $img['id'] ?>">
            <img src="<?= e($img['path']) ?>" alt="<?= e($img['alt']) ?>" class="aspect-square w-full rounded object-cover">
            <button class="absolute right-1 top-1 rounded bg-white/90 px-1.5 text-xs text-alert" aria-label="Xóa ảnh">✕</button>
          </form>
        <?php endforeach; ?>
      </div>
      <form method="post" action="/admin/products/<?= $p['id'] ?>/image" enctype="multipart/form-data" class="mt-3 space-y-2"><?= csrf_field() ?>
        <label class="label" for="image">Tải ảnh (JPG/PNG/WEBP ≤ 3MB)</label>
        <input id="image" type="file" name="image" accept="image/jpeg,image/png,image/webp" class="block w-full text-sm" required>
        <?= a_field('alt', 'Mô tả ảnh', '', $errors) ?>
        <button class="btn-ghost">Tải lên</button>
      </form>
    </section>

    <section class="a-card">
      <h2 class="text-lg">Sản phẩm mua kèm</h2>
      <ul class="mt-2 space-y-1 text-sm">
        <?php foreach ($relations as $r): ?>
          <li class="flex items-center gap-2"><span class="flex-1"><?= e($r['name']) ?> <?= status_badge($r['status']) ?> <?= $r['source'] === 'ai' ? '<span class="text-xs text-ink-mute">(AI đề xuất)</span>' : '' ?></span>
            <form method="post" action="/admin/products/<?= $p['id'] ?>/relation"><?= csrf_field() ?><input type="hidden" name="relation_id" value="<?= $r['id'] ?>"><input type="hidden" name="remove" value="1"><button class="text-xs text-alert underline">Bỏ</button></form></li>
        <?php endforeach; ?>
      </ul>
      <form method="post" action="/admin/products/<?= $p['id'] ?>/relation" class="mt-3 flex gap-2"><?= csrf_field() ?>
        <label class="sr-only" for="rel">Sản phẩm</label>
        <select id="rel" name="related_product_id" class="field"><?php foreach ($allProducts as $ap): if ((int)$ap['id'] === (int)$p['id']) continue; ?><option value="<?= $ap['id'] ?>"><?= e($ap['name']) ?></option><?php endforeach; ?></select>
        <button class="btn-ghost shrink-0">Thêm</button>
      </form>
    </section>

    <form method="post" action="/admin/products/<?= $p['id'] ?>/delete" data-confirm="Sản phẩm từng có trong đơn sẽ chuyển sang Ngừng bán; chưa có đơn sẽ bị xóa hẳn. Tiếp tục?"><?= csrf_field() ?>
      <button class="text-sm font-semibold text-alert underline">Xóa / ngừng bán sản phẩm</button>
    </form>
  </div>
  <?php endif; ?>
</div>
