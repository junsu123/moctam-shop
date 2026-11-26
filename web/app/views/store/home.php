<?php
$shelfArt = [
    'tra-tui-loc' => '/assets/img/products/tra-gung-mat-ong.svg',
    'bot-ngu-coc' => '/assets/img/products/bot-ngu-coc-25-loai-hat.svg',
    'bot-thien-nhien' => '/assets/img/products/bot-matcha-thai-nguyen.svg',
    'ca-phe' => '/assets/img/products/ca-phe-robusta-rang-moc.svg',
];
?>
<section class="wrap pt-10 pb-16 sm:pt-14">
  <div class="max-w-3xl">
    <h1 class="text-3xl leading-[1.08] sm:text-5xl">Trà, bột và cà phê làm tại xưởng, giao tới tận nhà.</h1>
    <p class="mt-4 max-w-[58ch] text-lg text-ink-soft">Sấy, rang, xay và đóng gói theo từng mẻ nhỏ. Chọn quy cách vừa dùng, xem phí giao ngay trong giỏ, trả tiền khi nhận hoặc chuyển khoản VietQR.</p>
  </div>

  <div class="shelf mt-10 grid grid-cols-2 gap-x-4 gap-y-6 sm:grid-cols-4 sm:gap-x-6">
    <?php foreach ($categories as $c): ?>
      <a href="<?= e(page_url($c['slug'])) ?>" class="group flex flex-col no-underline">
        <span class="relative block overflow-hidden rounded-t-2xl bg-white">
          <img src="<?= e($shelfArt[$c['slug']] ?? '/assets/img/placeholder.svg') ?>" alt="" width="400" height="400" class="aspect-[4/4] w-full object-cover transition-transform duration-300 group-hover:-translate-y-1">
        </span>
        <span class="tag-label -mt-1 bg-kraft-light px-4 py-3">
          <span class="block text-lg font-extrabold leading-tight text-coffee"><?= e($c['name']) ?></span>
          <span class="mt-0.5 block text-sm text-coffee-light"><?= (int)$c['product_count'] ?> sản phẩm</span>
        </span>
      </a>
    <?php endforeach; ?>
  </div>
</section>

<?php if ($flash && $flash['items']): ?>
<section class="bg-turmeric-light/70 py-10" aria-labelledby="fs-title">
  <div class="wrap">
    <div class="flex flex-wrap items-end justify-between gap-4">
      <div>
        <h2 id="fs-title" class="text-2xl"><?= e($flash['name']) ?></h2>
        <p class="mt-1 text-ink-soft">Kết thúc sau <strong class="tabular-nums text-ink" data-countdown="<?= e(\App\Core\Clock::toLocal($flash['ends_at'])->format(DATE_ATOM)) ?>">--:--:--</strong>. Giá áp dụng khi tạo đơn trước giờ kết thúc.</p>
      </div>
      <a href="<?= fixed_url('flash') ?>" class="btn-ghost">Xem tất cả</a>
    </div>
    <div class="mt-6 grid grid-cols-2 gap-4 sm:grid-cols-4">
      <?php foreach (array_slice($flash['items'], 0, 4) as $it): ?>
        <a href="<?= e(page_url($it['slug'])) ?>" class="flex flex-col rounded-xl bg-white p-3 no-underline hover:ring-2 hover:ring-turmeric">
          <img src="<?= e($it['image']) ?>" alt="<?= e($it['name']) ?>" width="400" height="400" loading="lazy" class="aspect-square w-full rounded-lg object-cover">
          <span class="mt-2 font-semibold text-ink"><?= e($it['name']) ?></span>
          <span class="text-sm text-ink-mute"><?= e($it['variant_label']) ?></span>
          <span class="mt-1 flex items-baseline gap-2"><span class="price text-turmeric-dark"><?= money($it['sale_price']) ?></span><span class="price-was text-sm"><?= money($it['price']) ?></span></span>
          <?php if ((int)$it['available'] <= 0): ?><span class="mt-1 text-xs font-semibold text-alert">Đã hết suất</span><?php elseif ((int)$it['available'] <= 10): ?><span class="mt-1 text-xs font-semibold text-coffee">Còn <?= (int)$it['available'] ?> sản phẩm</span><?php endif; ?>
        </a>
      <?php endforeach; ?>
    </div>
  </div>
</section>
<?php endif; ?>

<section class="wrap py-14" aria-labelledby="featured-title">
  <h2 id="featured-title" class="text-2xl">Xưởng gợi ý</h2>
  <div class="mt-6 grid grid-cols-2 gap-x-4 gap-y-8 sm:grid-cols-3 lg:grid-cols-4">
    <?php foreach ($featured as $p): ?><?= \App\Core\View::partial('store/_card', ['p' => $p]) ?><?php endforeach; ?>
  </div>
</section>

<section class="wrap grid gap-10 border-t border-ink/10 pt-12 lg:grid-cols-3">
  <div>
    <h2 class="text-xl">Mua hàng thế nào</h2>
    <ol class="mt-4 space-y-3 text-ink-soft">
      <li><strong class="text-ink">1. Chọn quy cách.</strong> Mỗi hộp, túi, hũ có giá và tồn kho riêng.</li>
      <li><strong class="text-ink">2. Xem tổng tiền.</strong> Chọn tỉnh/thành để biết phí giao, nhập mã giảm giá nếu có.</li>
      <li><strong class="text-ink">3. Đặt hàng.</strong> Không cần tài khoản. Trả tiền khi nhận, hoặc quét VietQR.</li>
    </ol>
  </div>
  <div class="lg:col-span-2">
    <div class="flex items-end justify-between">
      <h2 class="text-xl">Từ blog của xưởng</h2>
      <a href="<?= fixed_url('blog') ?>" class="text-sm font-semibold">Tất cả bài viết</a>
    </div>
    <div class="mt-4 grid gap-6 sm:grid-cols-2">
      <?php foreach (array_slice($posts, 0, 2) as $b): ?>
        <a href="<?= e(page_url($b['slug'])) ?>" class="block rounded-xl bg-white p-5 no-underline hover:ring-2 hover:ring-tea/30">
          <h3 class="text-lg text-ink"><?= e($b['pub_title']) ?></h3>
          <p class="mt-2 line-clamp-3 text-sm text-ink-soft"><?= e($b['pub_meta_description']) ?></p>
        </a>
      <?php endforeach; ?>
    </div>
  </div>
</section>
