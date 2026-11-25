<?php $title = 'Không thực hiện được'; ?>
<div class="a-card max-w-lg">
  <p class="text-3xl font-extrabold text-tea"><?= (int)$code ?></p>
  <p class="mt-2 font-semibold"><?= e($message) ?></p>
  <?php if ($code === 403): ?><p class="mt-2 text-sm text-ink-soft">Liên hệ quản trị viên nếu bạn cần được cấp quyền này.</p><?php endif; ?>
  <a href="/admin" class="btn-ghost mt-4">Về tổng quan</a>
</div>
