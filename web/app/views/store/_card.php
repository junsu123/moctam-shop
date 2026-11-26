<?php
/** @var array $p sản phẩm (id, name, slug, short_desc, min_price, image, available, flash) */
$soldOut = isset($p['available']) && (int)$p['available'] <= 0;
$hTag = ($h ?? 'h3') === 'h2' ? 'h2' : 'h3'; // h2 khi lưới nằm ngay dưới H1 (danh mục, tìm kiếm) — không nhảy bậc tiêu đề
?>
<article class="group flex flex-col">
  <a href="<?= e(page_url($p['slug'])) ?>" class="relative block overflow-hidden rounded-xl bg-white no-underline">
    <img src="<?= e($p['image'] ?: '/assets/img/placeholder.svg') ?>" alt="<?= e($p['name']) ?>" width="400" height="400" loading="lazy" class="aspect-square w-full object-cover transition-transform duration-300 group-hover:scale-[1.03] <?= $soldOut ? 'opacity-60' : '' ?>">
    <?php if (!empty($p['flash'])): ?>
      <span class="chip-sale absolute left-2 top-2">−<?= (int)round(100 - $p['flash']['sale'] * 100 / max(1, $p['flash']['list'])) ?>%</span>
    <?php endif; ?>
    <?php if ($soldOut): ?><span class="absolute bottom-2 left-2 rounded-md bg-ink px-2 py-0.5 text-xs font-semibold text-white">Tạm hết hàng</span><?php endif; ?>
  </a>
  <<?= $hTag ?> class="mt-3 text-base font-semibold leading-snug"><a href="<?= e(page_url($p['slug'])) ?>" class="text-ink no-underline hover:text-tea"><?= e($p['name']) ?></a></<?= $hTag ?>>
  <?php if (!empty($p['short_desc'])): ?><p class="mt-0.5 line-clamp-2 text-sm text-ink-mute"><?= e($p['short_desc']) ?></p><?php endif; ?>
  <p class="mt-1.5 flex flex-wrap items-baseline gap-x-2">
    <?php if (!empty($p['flash'])): ?>
      <span class="price text-turmeric-dark">từ <?= money($p['flash']['sale']) ?></span>
      <span class="price-was text-sm"><?= money($p['flash']['list']) ?></span>
    <?php else: ?>
      <span class="price text-ink">từ <?= money($p['min_price']) ?></span>
    <?php endif; ?>
  </p>
</article>
