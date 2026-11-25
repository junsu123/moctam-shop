<?php
$o = $order;
$isQr = $o['payment_method'] === 'vietqr';
$done = in_array($o['status'], ['cancelled'], true);
?>
<section class="wrap py-10" data-order-page data-order-code="<?= e($o['code']) ?>">
  <div class="max-w-3xl">
    <?php if ($done): ?>
      <h1 class="text-3xl">Đơn <?= e($o['code']) ?> đã hủy</h1>
      <p class="mt-2 text-ink-soft">Liên hệ hotline <?= e(setting('hotline')) ?> nếu bạn cần hỗ trợ.</p>
    <?php else: ?>
      <h1 class="text-3xl">Cảm ơn bạn, đơn <?= e($o['code']) ?> đã được tạo.</h1>
      <p class="mt-2 text-lg text-ink-soft">
        <?= $isQr ? 'Chuyển khoản theo mã QR bên dưới để xưởng chuẩn bị hàng. Đơn được giữ đến ' . e(vn_time($o['expires_at'], 'H:i d/m/Y')) . '.' : 'Xưởng sẽ gọi xác nhận trước khi giao. Bạn trả tiền khi nhận hàng.' ?>
      </p>
    <?php endif; ?>
    <p class="mt-3 text-sm text-ink-mute">Trạng thái: <strong class="text-ink"><?= e($o['status_label']) ?></strong>. Thanh toán: <strong class="text-ink"><?= e(\App\Domain\OrderService::PAYMENT_LABELS[$o['payment_status']]) ?></strong></p>
  </div>

  <div class="mt-8 grid gap-8 lg:grid-cols-[1fr_380px]">
    <div class="space-y-6">
      <?php if ($isQr && !$done && in_array($o['payment_status'], ['unpaid', 'partial'], true)): $q = $o['vietqr']; ?>
        <div class="grid gap-6 rounded-xl bg-white p-6 sm:grid-cols-[220px_1fr]">
          <div class="rounded-lg border border-ink/10 bg-white p-2" data-qr="<?= e($q['qr_payload']) ?>" role="img" aria-label="Mã VietQR chuyển <?= money($q['amount']) ?>"></div>
          <dl class="grid grid-cols-[auto_1fr] content-start gap-x-4 gap-y-2 text-sm">
            <dt class="text-ink-mute">Ngân hàng</dt><dd class="font-semibold"><?= e($q['bank_name']) ?></dd>
            <dt class="text-ink-mute">Số tài khoản</dt><dd class="font-semibold tabular-nums"><?= e($q['account_no']) ?> <button type="button" class="ml-1 text-xs font-semibold text-tea underline" data-copy="<?= e($q['account_no']) ?>">Sao chép</button></dd>
            <dt class="text-ink-mute">Chủ tài khoản</dt><dd class="font-semibold"><?= e($q['account_name']) ?></dd>
            <dt class="text-ink-mute">Số tiền</dt><dd class="price text-xl"><?= money($q['amount']) ?> <button type="button" class="ml-1 text-xs font-semibold text-tea underline" data-copy="<?= (int)$q['amount'] ?>">Sao chép</button></dd>
            <dt class="text-ink-mute">Nội dung</dt><dd class="text-lg font-extrabold tracking-wide text-tea"><?= e($q['content']) ?> <button type="button" class="ml-1 text-xs font-semibold underline" data-copy="<?= e($q['content']) ?>">Sao chép</button></dd>
          </dl>
          <p class="text-sm text-ink-soft sm:col-span-2">Giữ nguyên nội dung chuyển khoản để xưởng đối chiếu đúng đơn. Đơn được xác nhận sau khi nhân viên kiểm tra tiền về tài khoản — không cần gửi ảnh chụp.</p>
        </div>
      <?php endif; ?>

      <div class="rounded-xl bg-white p-6">
        <h2 class="text-xl">Giao đến</h2>
        <p class="mt-2"><strong><?= e($o['ship']['name']) ?></strong> — <?= e($o['ship']['phone']) ?></p>
        <p class="text-ink-soft"><?= e($o['ship']['address']) ?>, <?= e($o['ship']['province']) ?></p>
      </div>
      <p class="text-sm text-ink-soft">Lưu lại đường dẫn này để xem đơn sau: <a class="break-all" href="<?= e($o['confirm_url']) ?>"><?= e(rtrim((string)config('base_url'), '/') . $o['confirm_url']) ?></a></p>
    </div>

    <aside class="h-fit rounded-xl bg-white p-5">
      <h2 class="text-xl">Chi tiết đơn</h2>
      <ul class="mt-4 space-y-3 text-sm">
        <?php foreach ($o['items'] as $it): ?>
          <li class="flex justify-between gap-3">
            <span><span class="font-semibold"><?= e($it['product_name']) ?></span><br><span class="text-ink-mute"><?= e($it['variant_label']) ?> × <?= (int)$it['quantity'] ?></span></span>
            <span class="tabular-nums font-semibold"><?= money($it['line_total']) ?></span>
          </li>
        <?php endforeach; ?>
      </ul>
      <dl class="mt-4 space-y-2 border-t border-ink/10 pt-4 text-sm">
        <div class="flex justify-between"><dt class="text-ink-soft">Tiền hàng</dt><dd class="tabular-nums"><?= money($o['goods_subtotal']) ?></dd></div>
        <?php if ($o['voucher_discount'] > 0): ?><div class="flex justify-between"><dt class="text-ink-soft">Giảm giá (<?= e($o['voucher_code']) ?>)</dt><dd class="tabular-nums text-tea">−<?= money($o['voucher_discount']) ?></dd></div><?php endif; ?>
        <div class="flex justify-between"><dt class="text-ink-soft">Phí giao</dt><dd class="tabular-nums"><?= $o['shipping_fee'] > 0 ? money($o['shipping_fee']) : 'Miễn phí' ?></dd></div>
        <div class="flex items-baseline justify-between border-t border-ink/10 pt-3"><dt class="font-bold">Tổng thanh toán</dt><dd class="price text-2xl"><?= money($o['total']) ?></dd></div>
      </dl>
    </aside>
  </div>
</section>
<?php if ($isQr): ?><script src="<?= asset('js/qrcode.js') ?>" defer></script><?php endif; ?>
