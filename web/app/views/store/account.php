<?php
use App\Auth\OAuth;
use App\Domain\OrderService;
$err = fn($k) => isset($errors[$k]) ? '<p class="err-msg">' . e($errors[$k]) . '</p>' : '';
$linked = array_column($identities, 'provider');
?>
<section class="wrap py-10">
  <div class="flex flex-wrap items-end justify-between gap-4">
    <div>
      <h1 class="text-3xl">Chào <?= e($a['display_name']) ?></h1>
      <p class="mt-1 text-ink-soft"><?= $a['email'] ? e($a['email']) . ' — ' : '' ?>đăng nhập bằng <?= e(implode(', ', array_map(fn($p) => OAuth::LABELS[$p], $linked))) ?></p>
    </div>
    <form method="post" action="/tai-khoan/dang-xuat"><?= csrf_field() ?><button class="btn-ghost">Đăng xuất</button></form>
  </div>

  <?php foreach ($notices as $f): ?>
    <p class="mt-4 rounded-lg px-3 py-2 text-sm <?= $f['type'] === 'error' ? 'bg-alert-light text-alert' : 'bg-jade-200 text-tea-dark' ?>" role="<?= $f['type'] === 'error' ? 'alert' : 'status' ?>"><?= e($f['msg']) ?></p>
  <?php endforeach; ?>

  <div class="mt-8 grid gap-8 lg:grid-cols-[1fr_380px]">
    <section aria-labelledby="don-title">
      <h2 id="don-title" class="text-xl">Đơn hàng của tôi</h2>
      <?php if (!$orders): ?>
        <div class="mt-4 rounded-xl bg-white p-6">
          <p class="font-semibold">Chưa có đơn nào trong tài khoản.</p>
          <p class="mt-1 text-sm text-ink-soft">Đơn bạn đặt khi đang đăng nhập sẽ hiện ở đây. Đơn đặt trước đó (không đăng nhập) xem bằng đường dẫn trên trang xác nhận đơn.</p>
          <a href="/" class="btn-primary mt-4">Xem sản phẩm</a>
        </div>
      <?php else: ?>
        <ul class="mt-4 divide-y divide-ink/10 rounded-xl bg-white">
          <?php foreach ($orders as $o): ?>
            <li class="flex flex-wrap items-center gap-x-4 gap-y-1 p-4">
              <a href="/don-hang/<?= e($o['code']) ?>?t=<?= e($o['access_token']) ?>" class="font-mono font-semibold"><?= e($o['code']) ?></a>
              <span class="text-sm text-ink-mute"><?= vn_time($o['created_at'], 'd/m/Y') ?>, <?= (int)$o['line_count'] ?> sản phẩm</span>
              <span class="ml-auto font-bold tabular-nums"><?= money($o['total']) ?></span>
              <span class="w-full text-sm"><strong><?= e(OrderService::STATUS_LABELS[$o['status']]) ?></strong> — <?= e(strtoupper($o['payment_method'])) ?>, <?= e(mb_strtolower(OrderService::PAYMENT_LABELS[$o['payment_status']])) ?></span>
            </li>
          <?php endforeach; ?>
        </ul>
      <?php endif; ?>
    </section>

    <div class="space-y-6">
      <form method="post" action="/tai-khoan/thong-tin" class="rounded-xl bg-white p-5" id="thong-tin"><?= csrf_field() ?>
        <h2 class="text-lg">Thông tin giao hàng mặc định</h2>
        <p class="text-sm text-ink-mute">Được điền sẵn ở bước thanh toán; tự cập nhật theo đơn gần nhất.</p>
        <div class="mt-3 space-y-3">
          <div><label class="label" for="dn">Tên hiển thị</label><input id="dn" name="display_name" value="<?= e($a['display_name']) ?>" class="field" maxlength="120"><?= $err('display_name') ?></div>
          <div><label class="label" for="sn">Người nhận</label><input id="sn" name="ship_name" value="<?= e($a['ship_name']) ?>" class="field" maxlength="120" autocomplete="name"></div>
          <div><label class="label" for="sp">Số điện thoại</label><input id="sp" name="ship_phone" value="<?= e($a['ship_phone']) ?>" class="field" inputmode="tel" autocomplete="tel"><?= $err('ship_phone') ?></div>
          <div><label class="label" for="pv">Tỉnh/thành</label>
            <select id="pv" name="ship_province" class="field"><option value="">—</option><?php foreach ($provinces as $pv): ?><option <?= $pv === $a['ship_province'] ? 'selected' : '' ?>><?= e($pv) ?></option><?php endforeach; ?></select><?= $err('ship_province') ?></div>
          <div><label class="label" for="ad">Địa chỉ</label><input id="ad" name="ship_address" value="<?= e($a['ship_address']) ?>" class="field" maxlength="400" autocomplete="street-address"></div>
        </div>
        <button class="btn-primary mt-4">Lưu thông tin</button>
      </form>

      <section class="rounded-xl bg-white p-5" id="nhan-tin">
        <h2 class="text-lg">Nhận tin nhắc mua lại và ưu đãi</h2>
        <?php if ($consent === null): ?>
          <p class="mt-1 text-sm text-ink-soft">Bạn chọn ở bước đặt hàng. Sau khi có đơn, có thể bật/tắt tại đây.</p>
        <?php else: ?>
          <p class="mt-1 text-sm text-ink-soft">Hiện tại: <strong><?= $consent ? 'đang nhận' : 'không nhận' ?></strong> (qua điện thoại/Zalo theo số đã đặt hàng).</p>
          <form method="post" action="/tai-khoan/nhan-tin" class="mt-3"><?= csrf_field() ?>
            <input type="hidden" name="consent" value="<?= $consent ? '0' : '1' ?>">
            <button class="btn-ghost"><?= $consent ? 'Ngừng nhận tin' : 'Nhận tin' ?></button>
          </form>
        <?php endif; ?>
      </section>

      <?php $more = array_diff($providers, $linked); if ($more): ?>
      <section class="rounded-xl bg-white p-5">
        <h2 class="text-lg">Liên kết thêm</h2>
        <p class="mt-1 text-sm text-ink-soft">Để đăng nhập vào cùng tài khoản này bằng cách khác.</p>
        <div class="mt-3 flex flex-wrap gap-2"><?php foreach ($more as $p): ?><a class="btn-ghost" href="/auth/<?= e($p) ?>?next=/tai-khoan">Liên kết <?= e(OAuth::LABELS[$p]) ?></a><?php endforeach; ?></div>
      </section>
      <?php endif; ?>

      <form method="post" action="/tai-khoan/xoa" class="rounded-xl border border-alert/30 bg-white p-5" id="xoa"><?= csrf_field() ?>
        <h2 class="text-lg">Xóa tài khoản</h2>
        <p class="mt-1 text-sm text-ink-soft">Xóa thông tin đăng nhập và thông tin giao hàng đã lưu. Đơn đã đặt được giữ theo nghĩa vụ kế toán nhưng không còn gắn với bạn; bạn vẫn xem được bằng đường dẫn trên trang xác nhận đơn.</p>
        <label class="mt-3 flex items-start gap-2 text-sm"><input type="checkbox" name="confirm" value="1" class="mt-0.5 h-4 w-4 accent-tea"> Tôi hiểu và muốn xóa tài khoản</label>
        <button class="btn mt-3 bg-alert text-white hover:bg-alert/90">Xóa tài khoản</button>
      </form>
    </div>
  </div>
</section>
