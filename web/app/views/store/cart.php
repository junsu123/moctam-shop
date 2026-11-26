<section class="wrap py-10" data-cart-page>
  <h1 class="text-3xl">Giỏ hàng</h1>

  <div class="mt-8 hidden max-w-lg rounded-xl bg-white p-6" data-cart-empty>
    <p class="font-semibold">Giỏ hàng đang trống.</p>
    <p class="mt-1 text-ink-soft">Chọn sản phẩm và quy cách, rồi bấm "Thêm vào giỏ".</p>
    <a href="/" class="btn-primary mt-4">Xem sản phẩm</a>
  </div>

  <div class="mt-8 grid gap-8 lg:grid-cols-[1fr_380px]" data-cart-body>
    <div>
      <ul class="divide-y divide-ink/10 rounded-xl bg-white" data-cart-lines aria-live="polite">
        <li class="p-5 text-ink-mute">Đang tải giỏ hàng…</li>
      </ul>
      <div class="mt-4 hidden rounded-lg border border-alert/30 bg-alert-light p-4 text-sm text-alert" role="alert" data-cart-issues></div>
    </div>

    <aside class="h-fit rounded-xl bg-white p-5 lg:sticky lg:top-32" aria-labelledby="sum-title">
      <h2 id="sum-title" class="text-xl">Tạm tính</h2>
      <div class="mt-4">
        <label for="province" class="label">Giao đến tỉnh/thành</label>
        <select id="province" class="field" data-province>
          <option value="">— Chọn tỉnh/thành —</option>
          <?php foreach ($provinces as $pv): ?><option><?= e($pv) ?></option><?php endforeach; ?>
        </select>
      </div>
      <form class="mt-4" data-voucher-form>
        <label for="voucher" class="label">Mã giảm giá</label>
        <div class="flex gap-2">
          <input id="voucher" class="field uppercase" maxlength="40" autocomplete="off" placeholder="VD: CHAOBAN20" data-voucher>
          <button class="btn-ghost shrink-0">Áp dụng</button>
        </div>
        <p class="mt-1 text-sm" data-voucher-msg></p>
      </form>
      <?= \App\Core\View::partial('store/_totals') ?>
      <a href="<?= fixed_url('checkout') ?>" class="btn-primary mt-5 w-full" data-to-checkout>Đặt hàng</a>
      <p class="mt-3 text-xs text-ink-mute">Giá và tồn kho được máy chủ xác nhận lại khi đặt hàng.</p>
    </aside>
  </div>
</section>
