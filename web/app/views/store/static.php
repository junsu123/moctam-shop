<article class="wrap py-10">
  <h1 class="text-3xl"><?= e($c['pub_title']) ?></h1>
  <div class="prose-x mt-6"><?= $c['pub_body'] ?></div>
  <?php if ($c['slug'] === 'lien-he'): ?>
    <dl class="mt-6 grid max-w-md grid-cols-[auto_1fr] gap-x-6 gap-y-2 rounded-xl bg-white p-5">
      <dt class="text-ink-mute">Hotline</dt><dd class="font-semibold"><?= e(setting('hotline')) ?></dd>
      <dt class="text-ink-mute">Zalo</dt><dd class="font-semibold"><?= e(setting('zalo')) ?></dd>
      <dt class="text-ink-mute">Email</dt><dd class="font-semibold"><?= e(setting('support_email')) ?></dd>
      <dt class="text-ink-mute">Địa chỉ</dt><dd class="font-semibold"><?= e(setting('address')) ?></dd>
    </dl>
  <?php endif; ?>
</article>
