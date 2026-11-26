<?php $res = $result; ?>
<section class="wrap py-10">
  <h1 class="text-3xl"><?= e($heading) ?></h1>
  <?php if (!empty($intro)): ?><p class="mt-2 max-w-[60ch] text-ink-soft"><?= e($intro) ?></p><?php endif; ?>

  <?php if (isset($q)): ?>
    <form action="<?= fixed_url('search') ?>" class="mt-5 flex max-w-xl gap-2 md:hidden" role="search">
      <label for="q-page" class="sr-only">Tìm sản phẩm</label>
      <input id="q-page" name="q" value="<?= e($q) ?>" class="field" placeholder="Tên sản phẩm, mã SKU…">
      <button class="btn-primary">Tìm</button>
    </form>
  <?php endif; ?>

  <?php if (!isset($q)): ?>
  <form class="mt-6 flex items-center gap-2" method="get">
    <label for="sort" class="text-sm text-ink-soft">Sắp xếp</label>
    <select id="sort" name="sap-xep" class="field w-auto py-1.5 text-sm" data-autosubmit>
      <?php foreach (['default' => 'Nổi bật', 'price_asc' => 'Giá thấp đến cao', 'price_desc' => 'Giá cao đến thấp', 'newest' => 'Mới nhất'] as $k => $v): ?>
        <option value="<?= $k ?>" <?= $sort === $k ? 'selected' : '' ?>><?= $v ?></option>
      <?php endforeach; ?>
    </select>
    <noscript><button class="btn-ghost py-1.5">Áp dụng</button></noscript>
  </form>
  <?php endif; ?>

  <?php if (!$res['items']): ?>
    <div class="mt-10 max-w-lg rounded-xl bg-white p-6">
      <p class="font-semibold">Chưa có sản phẩm phù hợp.</p>
      <p class="mt-1 text-ink-soft">Thử từ khóa ngắn hơn, viết không dấu (VD: "tra gung"), hoặc xem các danh mục bên trên.</p>
    </div>
  <?php else: ?>
    <div class="mt-8 grid grid-cols-2 gap-x-4 gap-y-8 sm:grid-cols-3 lg:grid-cols-4">
      <?php foreach ($res['items'] as $p): ?><?= \App\Core\View::partial('store/_card', ['p' => $p, 'h' => $cardHeading ?? 'h3']) ?><?php endforeach; ?>
    </div>
    <?= \App\Core\View::partial('store/_pager', ['page' => $res['page'], 'pages' => $res['pages'], 'base' => $baseUrl, 'query' => $query + ($sort !== 'default' ? ['sap-xep' => $sort] : [])]) ?>
  <?php endif; ?>
</section>
