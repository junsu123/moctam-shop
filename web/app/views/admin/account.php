<div class="grid max-w-4xl gap-6 md:grid-cols-2">
  <section class="a-card">
    <h2 class="text-lg"><?= e($me['full_name']) ?></h2>
    <p class="text-sm text-ink-mute"><?= e($me['email']) ?> — <?= e($me['role_name']) ?></p>
    <h3 class="mt-4 font-semibold">Quyền hiện có</h3>
    <ul class="mt-2 list-disc pl-5 text-sm text-ink-soft">
      <?php foreach (\App\Core\Auth::PERMISSIONS as $k => $l): if (can($k)): ?><li><?= e($l) ?></li><?php endif; endforeach; ?>
    </ul>
  </section>
  <form method="post" action="/admin/account/password" class="a-card space-y-3"><?= csrf_field() ?>
    <h2 class="text-lg">Đổi mật khẩu</h2>
    <?= a_field('current', 'Mật khẩu hiện tại', '', $errors, ['type' => 'password', 'attrs' => 'autocomplete="current-password"']) ?>
    <?= a_field('new', 'Mật khẩu mới (≥ 10 ký tự)', '', $errors, ['type' => 'password', 'attrs' => 'autocomplete="new-password"']) ?>
    <button class="btn-primary">Đổi mật khẩu</button>
  </form>
</div>
