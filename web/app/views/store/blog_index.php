<section class="wrap py-10">
  <h1 class="text-3xl">Blog</h1>
  <p class="mt-2 text-ink-soft">Cách pha, cách bảo quản và chuyện nguyên liệu từ xưởng.</p>
  <?php if (!$result['items']): ?>
    <p class="mt-8 text-ink-soft">Chưa có bài viết nào.</p>
  <?php endif; ?>
  <div class="mt-8 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
    <?php foreach ($result['items'] as $b): ?>
      <article class="rounded-xl bg-white p-6">
        <p class="text-sm text-ink-mute"><time datetime="<?= e($b['published_at']) ?>"><?= vn_time($b['published_at'], 'd/m/Y') ?></time></p>
        <h2 class="mt-1 text-xl leading-snug"><a href="/blog/<?= e($b['slug']) ?>" class="text-ink no-underline hover:text-tea"><?= e($b['pub_title']) ?></a></h2>
        <p class="mt-2 line-clamp-3 text-ink-soft"><?= e($b['pub_meta_description']) ?></p>
      </article>
    <?php endforeach; ?>
  </div>
  <?= \App\Core\View::partial('store/_pager', ['page' => $result['page'], 'pages' => $result['pages'], 'base' => '/blog', 'query' => []]) ?>
</section>
