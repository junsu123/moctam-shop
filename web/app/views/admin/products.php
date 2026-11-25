<div class="flex flex-wrap items-end gap-3">
  <form class="flex flex-wrap items-end gap-3" method="get">
    <div><label class="label" for="q">Tìm</label><input id="q" name="q" value="<?= e($f['q'] ?? '') ?>" class="field" placeholder="Tên, SKU, từ khóa"></div>
    <div><label class="label" for="category">Danh mục</label><select id="category" name="category" class="field"><option value="">Tất cả</option><?php foreach ($cats as $c): ?><option value="<?= $c['id'] ?>" <?= (int)($f['category'] ?? 0) === (int)$c['id'] ? 'selected' : '' ?>><?= e($c['name']) ?></option><?php endforeach; ?></select></div>
    <div><label class="label" for="status">Trạng thái</label><select id="status" name="status" class="field"><option value="">Tất cả</option><option value="active">Đang bán</option><option value="draft">Nháp</option><option value="discontinued">Ngừng bán</option></select></div>
    <button class="btn-ghost">Lọc</button>
  </form>
  <a href="/admin/products/new" class="btn-primary ml-auto">Thêm sản phẩm</a>
</div>
<div class="a-card mt-4 overflow-x-auto p-0">
  <table class="a-table">
    <thead><tr><th></th><th>Sản phẩm</th><th>Danh mục</th><th class="text-right">Giá từ</th><th class="text-right">Số SKU</th><th>Trạng thái</th><th>Cập nhật</th></tr></thead>
    <tbody>
    <?php foreach ($rows as $p): ?>
      <tr>
        <td class="w-14"><img src="<?= e($p['image'] ?: '/assets/img/placeholder.svg') ?>" alt="" width="44" height="44" class="h-11 w-11 rounded object-cover"></td>
        <td><a href="/admin/products/<?= $p['id'] ?>" class="font-semibold"><?= e($p['name']) ?></a><?= $p['is_featured'] ? ' <span class="badge bg-turmeric-light text-coffee">Nổi bật</span>' : '' ?><br><span class="text-xs text-ink-mute">/san-pham/<?= e($p['slug']) ?></span></td>
        <td><?= e($p['cat']) ?></td>
        <td class="text-right tabular-nums"><?= $p['min_price'] ? money($p['min_price']) : '—' ?></td>
        <td class="text-right"><?= (int)$p['sku_count'] ?></td>
        <td><?= status_badge($p['status'], $p['status'] === 'draft' ? 'Nháp' : null) ?></td>
        <td class="whitespace-nowrap text-ink-mute"><?= vn_time($p['updated_at']) ?></td>
      </tr>
    <?php endforeach; ?>
    </tbody>
  </table>
</div>
