<section class="wrap py-10" data-checkout-page>
  <h1 class="text-3xl">Thanh toán</h1>
  <p class="mt-2 text-ink-soft">Không cần tạo tài khoản. Xưởng chỉ dùng thông tin này để giao đơn.</p>

  <div class="mt-8 hidden max-w-lg rounded-xl bg-white p-6" data-cart-empty>
    <p class="font-semibold">Giỏ hàng đang trống.</p>
    <a href="/" class="btn-primary mt-4">Xem sản phẩm</a>
  </div>

  <form class="mt-8 grid gap-8 lg:grid-cols-[1fr_400px]" novalidate data-checkout-form data-cart-body>
    <div class="space-y-8">
      <fieldset class="rounded-xl bg-white p-5 sm:p-6">
        <legend class="float-left mb-4 text-xl font-extrabold">1. Người nhận</legend>
        <div class="clear-both grid gap-4 sm:grid-cols-2">
          <div>
            <label for="f-name" class="label">Họ tên</label>
            <input id="f-name" name="name" class="field" autocomplete="name" maxlength="120" required aria-describedby="e-name">
            <p id="e-name" class="err-msg hidden" data-err="name"></p>
          </div>
          <div>
            <label for="f-phone" class="label">Số điện thoại</label>
            <input id="f-phone" name="phone" class="field" type="tel" inputmode="tel" autocomplete="tel" maxlength="15" required aria-describedby="e-phone" placeholder="0912 345 678">
            <p id="e-phone" class="err-msg hidden" data-err="phone"></p>
          </div>
          <div>
            <label for="f-province" class="label">Tỉnh/thành</label>
            <select id="f-province" name="province" class="field" required aria-describedby="e-province" data-province>
              <option value="">— Chọn tỉnh/thành —</option>
              <?php foreach ($provinces as $pv): ?><option><?= e($pv) ?></option><?php endforeach; ?>
            </select>
            <p id="e-province" class="err-msg hidden" data-err="province"></p>
          </div>
          <div class="sm:col-span-2">
            <label for="f-address" class="label">Địa chỉ nhận hàng</label>
            <input id="f-address" name="address" class="field" autocomplete="street-address" maxlength="400" required aria-describedby="e-address" placeholder="Số nhà, đường, phường/xã">
            <p id="e-address" class="err-msg hidden" data-err="address"></p>
          </div>
          <div class="sm:col-span-2">
            <label for="f-note" class="label">Ghi chú cho xưởng (không bắt buộc)</label>
            <textarea id="f-note" name="note" class="field" rows="2" maxlength="400" placeholder="VD: giao giờ hành chính"></textarea>
            <p class="err-msg hidden" data-err="note"></p>
          </div>
        </div>
      </fieldset>

      <fieldset class="rounded-xl bg-white p-5 sm:p-6">
        <legend class="float-left mb-4 text-xl font-extrabold">2. Thanh toán</legend>
        <div class="clear-both grid gap-3 sm:grid-cols-2">
          <label class="flex cursor-pointer gap-3 rounded-lg border-2 border-ink/15 p-4 has-[:checked]:border-tea has-[:checked]:bg-jade-50">
            <input type="radio" name="payment_method" value="cod" class="mt-1 accent-tea" checked>
            <span><span class="block font-semibold">Thanh toán khi nhận hàng</span><span class="text-sm text-ink-soft">Trả tiền mặt cho người giao.</span></span>
          </label>
          <label class="flex cursor-pointer gap-3 rounded-lg border-2 border-ink/15 p-4 has-[:checked]:border-tea has-[:checked]:bg-jade-50">
            <input type="radio" name="payment_method" value="vietqr" class="mt-1 accent-tea">
            <span><span class="block font-semibold">Chuyển khoản VietQR</span><span class="text-sm text-ink-soft">Quét mã sau khi đặt. Giữ hàng <?= (int)setting('hold_hours_vietqr', '24') ?> giờ.</span></span>
          </label>
        </div>
        <p class="err-msg hidden" data-err="payment_method"></p>
        <label class="mt-5 flex cursor-pointer items-start gap-3 text-sm text-ink-soft">
          <input type="checkbox" name="marketing_consent" value="1" class="mt-0.5 h-4 w-4 accent-tea">
          <span>Tôi đồng ý nhận tin nhắc mua lại và ưu đãi từ xưởng qua điện thoại/Zalo. Có thể hủy bất cứ lúc nào.</span>
        </label>
      </fieldset>
    </div>

    <aside class="h-fit rounded-xl bg-white p-5 lg:sticky lg:top-32">
      <h2 class="text-xl">3. Đơn hàng</h2>
      <ul class="mt-4 max-h-72 space-y-3 overflow-y-auto text-sm" data-summary-lines></ul>
      <div class="mt-4">
        <label for="voucher-c" class="label">Mã giảm giá</label>
        <div class="flex gap-2"><input id="voucher-c" class="field uppercase" maxlength="40" data-voucher><button type="button" class="btn-ghost shrink-0" data-voucher-apply>Áp dụng</button></div>
        <p class="mt-1 text-sm" data-voucher-msg></p>
      </div>
      <?= \App\Core\View::partial('store/_totals') ?>
      <div class="mt-4 hidden rounded-lg border border-alert/30 bg-alert-light p-3 text-sm text-alert" role="alert" data-form-error></div>
      <button class="btn-primary mt-5 w-full py-3 text-lg" data-place-order>Đặt hàng</button>
      <p class="mt-3 text-xs text-ink-mute">Bấm "Đặt hàng" là bạn đồng ý với <a href="/chinh-sach/doi-tra">chính sách đổi trả</a> và <a href="/chinh-sach/bao-mat">chính sách bảo mật</a>.</p>
    </aside>
  </form>

  <dialog class="w-[min(94vw,460px)] rounded-2xl p-0 backdrop:bg-ink/50" data-quote-dialog aria-labelledby="qd-title">
    <div class="p-6">
      <h2 id="qd-title" class="text-xl">Giá đã thay đổi</h2>
      <p class="mt-2 text-ink-soft" data-qd-msg>Giá hoặc ưu đãi vừa cập nhật. Vui lòng xem lại tổng tiền mới.</p>
      <dl class="mt-4 space-y-1 rounded-lg bg-jade-50 p-4 text-sm" data-qd-body></dl>
      <div class="mt-6 flex flex-wrap justify-end gap-2">
        <a href="/gio-hang" class="btn-ghost">Sửa giỏ hàng</a>
        <button type="button" class="btn-primary" data-qd-confirm>Đồng ý giá mới và đặt hàng</button>
      </div>
    </div>
  </dialog>
</section>
