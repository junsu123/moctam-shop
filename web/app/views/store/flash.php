<section class="wrap py-10">
  <?php if (!$flash || !$flash['items']): ?>
    <h1 class="text-3xl">Flash Sale</h1>
    <p class="mt-3 max-w-[60ch] text-ink-soft">Hiện chưa có chương trình nào đang diễn ra. Xem <a href="/">sản phẩm của xưởng</a> hoặc quay lại sau.</p>
  <?php else: ?>
    <h1 class="text-3xl"><?= e($flash['name']) ?></h1>
    <p class="mt-2 text-ink-soft">Kết thúc sau <strong class="tabular-nums text-ink" data-countdown="<?= e(\App\Core\Clock::toLocal($flash['ends_at'])->format(DATE_ATOM)) ?>">--:--:--</strong>. <?= $flash['allow_voucher'] ? 'Được dùng kèm mã giảm giá.' : 'Sản phẩm Flash Sale không tính vào điều kiện mã giảm giá.' ?></p>
    <div class="mt-8 grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
      <?php foreach ($flash['items'] as $it): ?>
        <a href="/san-pham/<?= e($it['slug']) ?>" class="flex flex-col rounded-xl bg-white p-3 no-underline hover:ring-2 hover:ring-turmeric">
          <img src="<?= e($it['image']) ?>" alt="<?= e($it['name']) ?>" width="400" height="400" loading="lazy" class="aspect-square w-full rounded-lg object-cover">
          <span class="mt-2 font-semibold text-ink"><?= e($it['name']) ?></span>
          <span class="text-sm text-ink-mute"><?= e($it['variant_label']) ?></span>
          <span class="mt-1 flex items-baseline gap-2"><span class="price text-turmeric-dark"><?= money($it['sale_price']) ?></span><span class="price-was text-sm"><?= money($it['price']) ?></span></span>
        </a>
      <?php endforeach; ?>
    </div>
  <?php endif; ?>
</section>
