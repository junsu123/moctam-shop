<article class="wrap py-10">
  <nav class="text-sm"><a href="<?= fixed_url('blog') ?>" class="text-ink-mute">Blog</a></nav>
  <h1 class="mt-3 max-w-[22ch] text-3xl sm:text-4xl"><?= e($c['pub_title']) ?></h1>
  <p class="mt-3 text-sm text-ink-mute">Đăng ngày <time datetime="<?= e($c['published_at']) ?>"><?= vn_time($c['published_at'], 'd/m/Y') ?></time></p>
  <div class="prose-x mt-6 text-lg"><?= $c['pub_body'] /* đã lọc HTML khi lưu */ ?></div>
  <?php if ($related): ?>
    <aside class="mt-12 max-w-sm">
      <h2 class="text-xl">Sản phẩm trong bài</h2>
      <div class="mt-4"><?= \App\Core\View::partial('store/_card', ['p' => $related[0]]) ?></div>
    </aside>
  <?php endif; ?>
</article>
