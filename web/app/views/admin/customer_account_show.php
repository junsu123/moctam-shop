<?php
use App\Domain\CustomerAccountService as Accounts;

$actions = [
    'account.locked' => 'Khóa đăng nhập', 'account.unlocked' => 'Mở khóa', 'account.sessions_revoked' => 'Buộc đăng xuất mọi thiết bị',
    'account.identity_unlinked' => 'Gỡ một cách đăng nhập', 'account.facebook_unlinked' => 'Facebook yêu cầu gỡ liên kết',
    'consent.granted' => 'Khách bật nhận tin', 'consent.withdrawn' => 'Khách tắt nhận tin',
];
$single = count($identities) <= 1;
?>
<div class="flex flex-wrap items-center gap-3">
  <a href="/admin/customer-accounts" class="text-sm">← Danh sách tài khoản khách</a>
  <?= $a['locked_at'] ? status_badge('failed', 'Đang khóa') : status_badge('active', 'Hoạt động') ?>
  <span class="text-sm text-ink-mute">Tạo lúc <?= vn_time($a['created_at']) ?></span>
</div>

<?php if ($a['locked_at']): ?>
  <div class="mt-4 flex flex-wrap items-center gap-3 rounded-lg border border-alert/30 bg-alert-light p-4 text-sm text-alert" role="alert">
    <span><strong>Đang khóa đăng nhập</strong> từ <?= vn_time($a['locked_at']) ?>: <?= e($a['locked_reason']) ?>. Khách vẫn mua hàng được khi không đăng nhập.</span>
    <form method="post" action="/admin/customer-accounts/<?= (int)$a['id'] ?>/unlock" class="ml-auto" data-confirm="Mở khóa để khách đăng nhập lại?"><?= csrf_field() ?><button class="btn-primary px-3 py-1.5 text-sm">Mở khóa</button></form>
  </div>
<?php endif; ?>

<div class="mt-4 grid gap-6 xl:grid-cols-[1fr_400px]">
  <div class="min-w-0 space-y-6">
    <section class="a-card">
      <h2 class="text-lg">Thông tin đăng nhập</h2>
      <dl class="mt-3 grid gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
        <div><dt class="text-ink-mute">Tên hiển thị</dt><dd class="font-semibold"><?= e($a['display_name']) ?></dd></div>
        <div><dt class="text-ink-mute">Email tài khoản (đã xác minh)</dt><dd><?= $a['email'] ? e($a['email']) : '<span class="text-ink-mute">không có — nhà cung cấp không cấp email</span>' ?></dd></div>
        <div><dt class="text-ink-mute">Đăng nhập gần nhất</dt><dd><?= $a['last_login_at'] ? vn_time($a['last_login_at']) : 'chưa' ?></dd></div>
        <div><dt class="text-ink-mute">Nhận tin chăm sóc, ưu đãi</dt><dd><?= $consent === null ? 'chưa có đơn' : ($consent ? 'Đồng ý' : 'Không đồng ý') ?> <span class="text-xs text-ink-mute">(khách tự đổi trên trang tài khoản)</span></dd></div>
      </dl>
      <p class="mt-3 text-xs text-ink-mute">Website không lưu mật khẩu của khách và không giữ mã truy cập Google/Facebook. Nhân viên không đổi được email hay cách đăng nhập thay khách; khách tự liên kết thêm trên trang Tài khoản của tôi.</p>
    </section>

    <section class="a-card overflow-x-auto">
      <h2 class="text-lg">Cách đăng nhập đã liên kết</h2>
      <table class="a-table mt-3">
        <thead><tr><th>Nhà cung cấp</th><th>Email từ nhà cung cấp</th><th>Liên kết lúc</th><th>Đăng nhập gần nhất</th><th></th></tr></thead>
        <tbody>
        <?php foreach ($identities as $i): ?>
          <tr>
            <td class="font-semibold"><?= e(Accounts::PROVIDER_LABELS[$i['provider']] ?? $i['provider']) ?></td>
            <td><?= $i['email'] ? e($i['email']) . ' ' . ($i['email_verified'] ? status_badge('approved', 'Đã xác minh') : status_badge('draft', 'Chưa xác minh')) : '<span class="text-ink-mute">không cấp</span>' ?></td>
            <td class="whitespace-nowrap"><?= vn_time($i['created_at']) ?></td>
            <td class="whitespace-nowrap"><?= $i['last_login_at'] ? vn_time($i['last_login_at']) : '' ?></td>
            <td class="text-right">
              <?php if (!$single): ?>
                <form method="post" action="/admin/customer-accounts/<?= (int)$a['id'] ?>/unlink" data-confirm="Gỡ đăng nhập bằng <?= e(Accounts::PROVIDER_LABELS[$i['provider']] ?? $i['provider']) ?>? Khách sẽ bị đăng xuất khỏi mọi thiết bị."><?= csrf_field() ?><input type="hidden" name="identity_id" value="<?= (int)$i['id'] ?>"><button class="btn-ghost px-3 py-1 text-xs">Gỡ liên kết</button></form>
              <?php endif; ?>
            </td>
          </tr>
        <?php endforeach; ?>
        <?php if (!$identities): ?><tr><td colspan="5" class="text-ink-mute">Không còn cách đăng nhập nào.</td></tr><?php endif; ?>
        </tbody>
      </table>
      <?php if ($single && $identities): ?><p class="mt-2 text-xs text-ink-mute">Đây là cách đăng nhập duy nhất nên không gỡ được. Muốn ngừng hẳn, dùng Khóa đăng nhập hoặc Xóa tài khoản.</p><?php endif; ?>
    </section>

    <section class="a-card overflow-x-auto">
      <h2 class="text-lg">Đơn đặt khi đăng nhập <span class="text-sm font-normal text-ink-mute">(<?= (int)$orderCount ?>)</span></h2>
      <table class="a-table mt-3">
        <thead><tr><th>Mã đơn</th><th>Trạng thái</th><th>Thanh toán</th><th class="text-right">Tổng</th><th>Đặt lúc</th></tr></thead>
        <tbody>
        <?php foreach ($orders as $o): ?>
          <tr>
            <td class="font-mono"><?php if (can('orders.view')): ?><a href="/admin/orders/<?= (int)$o['id'] ?>"><?= e($o['code']) ?></a><?php else: ?><?= e($o['code']) ?><?php endif; ?></td>
            <td><?= status_badge($o['status']) ?></td>
            <td><?= status_badge($o['payment_status']) ?></td>
            <td class="text-right tabular-nums"><?= money($o['total']) ?></td>
            <td class="whitespace-nowrap"><?= vn_time($o['created_at']) ?></td>
          </tr>
        <?php endforeach; ?>
        <?php if (!$orders): ?><tr><td colspan="5" class="text-ink-mute">Chưa có đơn. Đơn đặt khi không đăng nhập không được gắn vào tài khoản.</td></tr><?php endif; ?>
        </tbody>
      </table>
    </section>

    <section class="a-card">
      <h2 class="text-lg">Lịch sử thao tác</h2>
      <?php if ($history): ?>
      <ol class="mt-3 space-y-2 border-l-2 border-jade-200 pl-4 text-sm">
        <?php foreach ($history as $h): ?>
          <li><span class="font-semibold"><?= e($actions[$h['action']] ?? $h['action']) ?></span>
            <span class="text-ink-mute">— <?= vn_time($h['created_at']) ?>, <?= e($h['actor_type'] === 'user' ? ($h['full_name'] ?? 'nhân viên') : 'hệ thống / khách') ?></span>
            <?php if ($h['note']): ?><br><span class="text-ink-soft"><?= e($h['note']) ?></span><?php endif; ?></li>
        <?php endforeach; ?>
      </ol>
      <?php else: ?><p class="mt-2 text-sm text-ink-mute">Chưa có thao tác nào.</p><?php endif; ?>
    </section>
  </div>

  <aside class="space-y-6">
    <section class="a-card">
      <h2 class="text-lg">Phiên đăng nhập</h2>
      <p class="mt-2 text-sm text-ink-soft">Dùng khi khách báo đánh rơi điện thoại hoặc đăng nhập trên máy lạ. Khách vẫn đăng nhập lại được ngay sau đó.</p>
      <form method="post" action="/admin/customer-accounts/<?= (int)$a['id'] ?>/logout" class="mt-3" data-confirm="Đăng xuất khách khỏi mọi thiết bị?"><?= csrf_field() ?><button class="btn-ghost w-full" <?= $a['locked_at'] ? 'disabled' : '' ?>>Buộc đăng xuất mọi thiết bị</button></form>
    </section>

    <?php if (!$a['locked_at']): ?>
    <section class="a-card">
      <h2 class="text-lg">Khóa đăng nhập</h2>
      <p class="mt-2 text-sm text-ink-soft">Chặn đăng nhập (kể cả bằng nhà cung cấp khác cùng email) và đăng xuất ngay mọi phiên. Không ảnh hưởng đơn đã đặt; khách vẫn mua được khi không đăng nhập.</p>
      <form method="post" action="/admin/customer-accounts/<?= (int)$a['id'] ?>/lock" class="mt-3 space-y-3" data-confirm="Khóa đăng nhập tài khoản này?"><?= csrf_field() ?>
        <?= a_field('reason', 'Lý do (ghi nhật ký)', $old['reason'] ?? '', $errors, ['type' => 'textarea', 'rows' => 2, 'attrs' => 'maxlength="255"', 'hint' => 'VD: khách báo mất tài khoản Google, gọi hotline 26/11']) ?>
        <button class="btn-primary w-full">Khóa đăng nhập</button>
      </form>
    </section>
    <?php endif; ?>

    <section class="a-card">
      <h2 class="text-lg">Thông tin giao hàng mặc định</h2>
      <?php if ($a['ship_name'] || $a['ship_phone'] || $a['ship_address']): ?>
        <dl class="mt-3 space-y-1 text-sm">
          <div><dt class="inline text-ink-mute">Người nhận:</dt> <dd class="inline"><?= e($a['ship_name'] ?? '') ?></dd></div>
          <div><dt class="inline text-ink-mute">SĐT:</dt> <dd class="inline"><?= e($a['ship_phone'] ?? '') ?></dd></div>
          <div><dt class="inline text-ink-mute">Địa chỉ:</dt> <dd class="inline"><?= e(trim(($a['ship_address'] ?? '') . ', ' . ($a['ship_province'] ?? ''), ', ')) ?></dd></div>
        </dl>
        <p class="mt-2 text-xs text-ink-mute">Chỉ để điền sẵn khi khách thanh toán. Khách tự sửa trên trang tài khoản.</p>
      <?php else: ?><p class="mt-2 text-sm text-ink-mute">Chưa có.</p><?php endif; ?>
    </section>

    <section class="a-card border border-alert/30">
      <h2 class="text-lg text-alert">Xóa tài khoản theo yêu cầu của khách</h2>
      <p class="mt-2 text-sm text-ink-soft">Xóa hồ sơ và mọi cách đăng nhập. Đơn hàng vẫn được giữ (nghĩa vụ kế toán) nhưng không còn gắn tài khoản. Không hoàn tác được. Hệ thống cấp mã xác nhận để gửi cho khách.</p>
      <form method="post" action="/admin/customer-accounts/<?= (int)$a['id'] ?>/delete" class="mt-3 space-y-3" data-confirm="Xóa vĩnh viễn tài khoản này?"><?= csrf_field() ?>
        <?= a_field('delete_reason', 'Khách yêu cầu qua kênh nào, khi nào', $old['delete_reason'] ?? '', $errors, ['attrs' => 'maxlength="255"']) ?>
        <?= a_check('confirm', 'Tôi đã xác minh đúng người yêu cầu là chủ tài khoản', false) ?>
        <?php if (!empty($errors['confirm'])): ?><p class="err-msg"><?= e($errors['confirm']) ?></p><?php endif; ?>
        <button class="btn w-full bg-alert text-white hover:opacity-90">Xóa tài khoản</button>
      </form>
    </section>
  </aside>
</div>
