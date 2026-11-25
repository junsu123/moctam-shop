<?php if ($pages > 1): ?>
<nav class="mt-10 flex flex-wrap items-center gap-1" aria-label="Phân trang">
  <?php for ($i = 1; $i <= $pages; $i++): ?>
    <?php if ($i === $page): ?>
      <span class="rounded-lg bg-tea px-3.5 py-2 text-sm font-bold text-white" aria-current="page"><?= $i ?></span>
    <?php else: ?>
      <a href="<?= e(url($base, $query + ['trang' => $i])) ?>" class="rounded-lg bg-white px-3.5 py-2 text-sm font-semibold text-ink no-underline hover:bg-jade-200"><?= $i ?></a>
    <?php endif; ?>
  <?php endfor; ?>
</nav>
<?php endif; ?>
