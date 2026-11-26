<section class="wrap py-20">
  <p class="text-5xl font-extrabold text-tea"><?= (int)$code ?></p>
  <h1 class="mt-3 text-2xl"><?= e($message) ?></h1>
  <p class="mt-3 text-ink-soft">Tìm sản phẩm khác hoặc quay về trang chủ.</p>
  <div class="mt-6 flex gap-3"><a href="/" class="btn-primary">Về trang chủ</a><a href="<?= fixed_url('search') ?>" class="btn-ghost">Tìm sản phẩm</a></div>
</section>
