<?php use App\Core\Auth; ?>
<p class="max-w-3xl text-sm text-ink-soft">Máy chủ kiểm tra quyền trên từng thao tác — ẩn nút trên giao diện chỉ để gọn, không phải lớp bảo vệ. Mọi thay đổi quyền được ghi nhật ký.</p>
<div class="mt-4 grid gap-4 lg:grid-cols-2">
  <?php foreach ($roles as $r): $perms = json_dec($r['permissions']); ?>
    <form method="post" action="/admin/roles/save" class="a-card"><?= csrf_field() ?>
      <input type="hidden" name="code" value="<?= e($r['code']) ?>">
      <div class="flex items-center gap-3"><h2 class="text-lg"><?= e($r['name']) ?></h2><span class="text-sm text-ink-mute"><?= (int)$r['n'] ?> người</span></div>
      <?php if ($r['code'] === 'admin'): ?>
        <p class="mt-2 text-sm text-ink-soft">Toàn quyền. Không chỉnh sửa được.</p>
      <?php else: ?>
        <div class="mt-3 grid gap-1 sm:grid-cols-2">
          <?php foreach (Auth::PERMISSIONS as $k => $label): ?><label class="text-sm"><input type="checkbox" name="perms[]" value="<?= $k ?>" class="accent-tea" <?= in_array($k, $perms, true) ? 'checked' : '' ?>> <?= e($label) ?></label><?php endforeach; ?>
        </div>
        <button class="btn-ghost mt-3">Lưu quyền</button>
      <?php endif; ?>
    </form>
  <?php endforeach; ?>
</div>
