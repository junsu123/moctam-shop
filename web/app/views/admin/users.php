<?php
use App\Core\Auth;
$roleOpts = array_column($roles, 'name', 'code');
$userForm = function (?array $u) use ($roleOpts, $errors, $old) {
    $v = fn($k, $d = '') => $old[$k] ?? ($u[$k] ?? $d);
    $extra = json_dec($u['extra_permissions'] ?? '[]');
    ob_start(); ?>
    <form method="post" action="/admin/users/save" class="grid gap-3 sm:grid-cols-2"><?= csrf_field() ?>
      <input type="hidden" name="id" value="<?= (int)($u['id'] ?? 0) ?>">
      <?= a_field('full_name', 'Họ tên', $v('full_name'), $u ? [] : $errors) ?>
      <?= a_field('email', 'Email đăng nhập', $v('email'), $u ? [] : $errors, ['type' => 'email']) ?>
      <?= a_field('role_code', 'Vai trò', $v('role_code', 'operations'), $u ? [] : $errors, ['type' => 'select', 'options' => $roleOpts]) ?>
      <?= a_field('password', $u ? 'Mật khẩu mới (để trống nếu không đổi)' : 'Mật khẩu (≥ 10 ký tự)', '', $u ? [] : $errors, ['type' => 'password', 'attrs' => 'autocomplete="new-password"']) ?>
      <details class="sm:col-span-2"><summary class="cursor-pointer text-sm font-semibold text-tea">Cấp thêm quyền riêng</summary>
        <div class="mt-2 grid gap-1 sm:grid-cols-2"><?php foreach (Auth::PERMISSIONS as $k => $label): ?><label class="text-sm"><input type="checkbox" name="extra[]" value="<?= $k ?>" class="accent-tea" <?= in_array($k, $extra, true) ? 'checked' : '' ?>> <?= e($label) ?></label><?php endforeach; ?></div>
      </details>
      <div class="flex items-center gap-4 sm:col-span-2"><?= a_check('is_active', 'Đang hoạt động', (bool)$v('is_active', 1)) ?><button class="btn-primary ml-auto"><?= $u ? 'Lưu' : 'Tạo tài khoản' ?></button></div>
    </form>
    <?php return ob_get_clean();
};
?>
<div class="grid gap-6 xl:grid-cols-[1fr_420px]">
  <div class="space-y-3">
    <?php foreach ($users as $u):
      $tempLocked = $u['locked_until'] && $u['locked_until'] > \App\Core\Clock::nowDb(); ?>
      <details class="a-card">
        <summary class="flex cursor-pointer flex-wrap items-center gap-3"><span class="font-semibold"><?= e($u['full_name']) ?></span><span class="text-sm text-ink-mute"><?= e($u['email']) ?></span><span class="badge bg-jade-200 text-tea-dark"><?= e($u['role_name']) ?></span><?= $u['is_active'] ? '' : status_badge('discontinued', 'Đã khóa') ?><?= $tempLocked ? status_badge('failed', 'Tạm khóa do sai mật khẩu') : '' ?><span class="ml-auto text-xs text-ink-mute">Đăng nhập cuối: <?= $u['last_login_at'] ? vn_time($u['last_login_at']) : 'chưa' ?></span></summary>
        <?php if ($tempLocked || (int)$u['failed_logins'] > 0): ?>
          <div class="mt-4 flex flex-wrap items-center gap-3 rounded-lg bg-alert-light px-4 py-3 text-sm text-alert">
            <span><?= (int)$u['failed_logins'] ?> lần nhập sai mật khẩu liên tiếp<?= $tempLocked ? ', tự mở khóa lúc ' . vn_time($u['locked_until']) : '' ?>.</span>
            <form method="post" action="/admin/users/<?= (int)$u['id'] ?>/unlock" class="ml-auto"><?= csrf_field() ?><button class="btn-ghost px-3 py-1 text-xs">Mở khóa ngay</button></form>
          </div>
        <?php endif; ?>
        <div class="mt-4"><?= $userForm($u) ?></div>
      </details>
    <?php endforeach; ?>
  </div>
  <section class="a-card h-fit"><h2 class="text-lg">Thêm nhân viên</h2><div class="mt-3"><?= $userForm(null) ?></div></section>
</div>
