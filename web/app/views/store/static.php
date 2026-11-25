<?php
use App\Domain\LegalPages;

$body = LegalPages::render((string)$c['pub_body']);
// Mục lục từ các tiêu đề h2 có id (văn bản dài như chính sách, điều khoản)
preg_match_all('#<h2 id="([a-z0-9\-]+)">(.*?)</h2>#u', $body, $mm, PREG_SET_ORDER);
$toc = count($mm) >= 4 ? $mm : [];
$effective = \App\Core\Db::val('SELECT created_at FROM content_versions WHERE id = :v', ['v' => (int)$c['published_version_id']]) ?: $c['published_at'];
?>
<article class="wrap py-10">
  <h1 class="text-3xl"><?= e($c['pub_title']) ?></h1>
  <?php if ($effective && $toc): ?><p class="mt-2 text-sm text-ink-mute">Có hiệu lực từ <?= vn_time((string)$effective, 'd/m/Y') ?></p><?php endif; ?>

  <div class="<?= $toc ? 'mt-8 lg:grid lg:grid-cols-[240px_1fr] lg:gap-12' : 'mt-6' ?>">
    <?php if ($toc): ?>
      <details class="mb-6 rounded-xl bg-white p-4 text-sm lg:hidden">
        <summary class="cursor-pointer font-semibold">Nội dung (<?= count($toc) ?> mục)</summary>
        <ol class="mt-2 space-y-1.5"><?php foreach ($toc as $t): ?><li><a href="#<?= e($t[1]) ?>" class="text-ink-soft no-underline"><?= strip_tags($t[2]) ?></a></li><?php endforeach; ?></ol>
      </details>
      <nav class="hidden h-fit rounded-xl bg-white p-5 text-sm lg:sticky lg:top-32 lg:block" aria-label="Mục lục">
        <p class="font-semibold">Nội dung</p>
        <ol class="mt-2 space-y-1.5">
          <?php foreach ($toc as $t): ?><li><a href="#<?= e($t[1]) ?>" class="text-ink-soft no-underline hover:text-tea"><?= strip_tags($t[2]) ?></a></li><?php endforeach; ?>
        </ol>
      </nav>
    <?php endif; ?>

    <div class="min-w-0">
      <div class="prose-x [&_h2]:scroll-mt-32"><?= $body /* đã lọc HTML khi lưu; biến được mã hóa khi chèn */ ?></div>

      <?php if ($c['slug'] === 'bao-mat'): ?>
        <div class="mt-8 max-w-[68ch] rounded-xl bg-white p-5">
          <p class="font-semibold">Thông tin đang lưu trên trình duyệt này</p>
          <p class="mt-1 text-sm text-ink-soft">Giỏ hàng, tỉnh/thành, mã giảm giá và họ tên, số điện thoại, địa chỉ của lần đặt trước. Thao tác dưới đây không ảnh hưởng tới đơn bạn đã đặt.</p>
          <button type="button" class="btn-ghost mt-3" data-clear-local>Xóa thông tin đã lưu trên trình duyệt này</button>
        </div>
      <?php endif; ?>

      <?php if ($c['slug'] === 'lien-he'): ?>
        <dl class="mt-6 grid max-w-md grid-cols-[auto_1fr] gap-x-6 gap-y-2 rounded-xl bg-white p-5">
          <dt class="text-ink-mute">Hotline</dt><dd class="font-semibold"><?= e(setting('hotline')) ?></dd>
          <dt class="text-ink-mute">Zalo</dt><dd class="font-semibold"><?= e(setting('zalo')) ?></dd>
          <dt class="text-ink-mute">Email</dt><dd class="font-semibold"><?= e(setting('support_email')) ?></dd>
          <dt class="text-ink-mute">Địa chỉ</dt><dd class="font-semibold"><?= e(setting('address')) ?></dd>
        </dl>
      <?php endif; ?>
    </div>
  </div>
</article>
