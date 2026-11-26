<?php
$skus = $p['skus'];
$first = null;
foreach ($skus as $s) { if ($s['available'] > 0) { $first = $s; break; } }
$first ??= $skus[0] ?? null;
$info = [
    'Thành phần' => $p['ingredients'], 'Cách dùng' => $p['usage_guide'],
    'Bảo quản' => $p['storage_guide'], 'Thông tin dị ứng' => $p['allergens'],
];
?>
<div class="wrap py-8">
  <nav class="text-sm text-ink-mute" aria-label="Đường dẫn">
    <a href="/" class="text-ink-mute">Trang chủ</a> /
    <a href="<?= e(page_url($p['category_slug'])) ?>" class="text-ink-mute"><?= e($p['category_name']) ?></a>
  </nav>

  <div class="mt-4 grid gap-8 lg:grid-cols-2 lg:gap-14">
    <div>
      <img src="<?= e($p['images'][0]['path'] ?? '/assets/img/placeholder.svg') ?>" alt="<?= e($p['images'][0]['alt'] ?? $p['name']) ?>" width="600" height="600" class="aspect-square w-full rounded-2xl bg-white object-cover" data-main-img>
      <?php if (count($p['images']) > 1): ?>
        <div class="mt-3 flex gap-2">
          <?php foreach ($p['images'] as $img): ?>
            <button type="button" class="overflow-hidden rounded-lg ring-tea focus:ring-2" data-thumb="<?= e($img['path']) ?>"><img src="<?= e($img['path']) ?>" alt="" width="72" height="72" class="h-18 w-18 object-cover"></button>
          <?php endforeach; ?>
        </div>
      <?php endif; ?>
    </div>

    <div data-product='<?= e(json_enc(['id' => (int)$p['id'], 'name' => $p['name'], 'slug' => $p['slug'], 'image' => $p['images'][0]['path'] ?? null, 'skus' => $skus])) ?>'>
      <h1 class="text-3xl sm:text-4xl"><?= e($p['name']) ?></h1>
      <?php if ($p['short_desc']): ?><p class="mt-2 text-lg text-ink-soft"><?= e($p['short_desc']) ?></p><?php endif; ?>
      <?php if ($p['sold_count'] > 0): ?><p class="mt-2 text-sm text-ink-mute">Đã bán <?= number_format($p['sold_count'], 0, ',', '.') ?> sản phẩm (đơn đã giao)</p><?php endif; ?>

      <?php if (!$skus): ?>
        <p class="mt-6 rounded-lg bg-white p-4">Sản phẩm tạm thời chưa mở bán.</p>
      <?php else: ?>
      <div class="mt-6 flex flex-wrap items-baseline gap-3" aria-live="polite">
        <span class="price text-3xl" data-price><?= money($first['sale_price'] ?? $first['price']) ?></span>
        <span class="price-was text-lg <?= $first['sale_price'] === null ? 'hidden' : '' ?>" data-price-was><?= money($first['price']) ?></span>
        <span class="chip-sale <?= $first['sale_price'] === null ? 'hidden' : '' ?>" data-flash-chip>Flash Sale</span>
      </div>
      <p class="mt-1 text-sm text-ink-mute <?= $first['flash_ends_at'] ? '' : 'hidden' ?>" data-flash-note>Giá Flash Sale đến <span data-flash-end><?= $first['flash_ends_at'] ? vn_time($first['flash_ends_at'], 'H:i d/m') : '' ?></span></p>

      <fieldset class="mt-6">
        <legend class="label">Quy cách</legend>
        <div class="flex flex-wrap gap-2">
          <?php foreach ($skus as $s): ?>
            <label class="variant cursor-pointer">
              <input type="radio" name="sku" value="<?= (int)$s['id'] ?>" class="sr-only" <?= $s['id'] === $first['id'] ? 'checked' : '' ?>>
              <span class="block rounded-lg border-2 border-ink/15 bg-white px-4 py-2 text-sm font-semibold <?= $s['available'] <= 0 ? 'text-ink-mute line-through decoration-1' : '' ?>"><?= e($s['variant_label']) ?></span>
            </label>
          <?php endforeach; ?>
        </div>
      </fieldset>
      <dl class="mt-4 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
        <dt class="text-ink-mute">Mã SKU</dt><dd class="font-medium" data-sku-code><?= e($first['sku_code']) ?></dd>
        <dt class="text-ink-mute">Khối lượng</dt><dd class="font-medium" data-weight><?= $first['net_weight_g'] ? (int)$first['net_weight_g'] . ' g' : '—' ?></dd>
        <dt class="text-ink-mute">Tình trạng</dt><dd class="font-semibold" data-stock></dd>
      </dl>

      <div class="mt-6 flex flex-wrap items-stretch gap-3">
        <div class="flex items-center rounded-lg border border-ink/20 bg-white">
          <button type="button" class="px-3 py-2 text-lg" data-qty-dec aria-label="Giảm số lượng">−</button>
          <label for="qty" class="sr-only">Số lượng</label>
          <input id="qty" type="number" min="1" max="99" value="1" inputmode="numeric" class="w-14 border-0 bg-transparent text-center font-semibold focus:outline-none" data-qty>
          <button type="button" class="px-3 py-2 text-lg" data-qty-inc aria-label="Tăng số lượng">+</button>
        </div>
        <button type="button" class="btn-primary flex-1 sm:flex-none" data-add-to-cart>Thêm vào giỏ</button>
        <button type="button" class="btn-ghost" data-buy-now>Mua ngay</button>
      </div>
      <?php endif; ?>

      <div class="mt-8 divide-y divide-ink/10 rounded-xl bg-white">
        <?php foreach ($info as $label => $val): if (!trim((string)$val)) continue; ?>
          <details class="group px-5 py-4" <?= $label === 'Thành phần' ? 'open' : '' ?>>
            <summary class="flex cursor-pointer list-none items-center justify-between font-semibold"><?= e($label) ?><span class="text-ink-mute transition-transform group-open:rotate-45" aria-hidden="true">+</span></summary>
            <p class="mt-2 whitespace-pre-line text-ink-soft"><?= e($val) ?></p>
          </details>
        <?php endforeach; ?>
      </div>
    </div>
  </div>

  <?php if (trim(strip_tags((string)$p['description']))): ?>
    <section class="mt-14 max-w-3xl">
      <h2 class="text-2xl">Về sản phẩm</h2>
      <div class="prose-x mt-3"><?= $p['description'] /* đã lọc HTML khi lưu */ ?></div>
    </section>
  <?php endif; ?>

  <?php if ($p['related']): ?>
    <section class="mt-14" aria-labelledby="rel-title">
      <h2 id="rel-title" class="text-2xl">Thường mua kèm</h2>
      <div class="mt-6 grid grid-cols-2 gap-x-4 gap-y-8 sm:grid-cols-4">
        <?php foreach ($p['related'] as $r): ?><?= \App\Core\View::partial('store/_card', ['p' => $r]) ?><?php endforeach; ?>
      </div>
    </section>
  <?php endif; ?>

  <?php if ($faqs): ?>
    <section class="mt-14 max-w-3xl">
      <h2 class="text-2xl">Câu hỏi thường gặp</h2>
      <div class="mt-4 divide-y divide-ink/10 rounded-xl bg-white">
        <?php foreach ($faqs as $f): ?>
          <details class="px-5 py-4"><summary class="cursor-pointer font-semibold"><?= e($f['pub_title']) ?></summary><div class="prose-x mt-2"><?= $f['pub_body'] ?></div></details>
        <?php endforeach; ?>
      </div>
    </section>
  <?php endif; ?>
</div>
