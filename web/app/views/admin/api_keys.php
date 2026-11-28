<?php if ($newKey): ?>
  <div class="a-card mb-6 border-2 border-turmeric" role="alert">
    <p class="font-semibold">Khóa mới "<?= e($newKey['name']) ?>" — sao chép vào cấu hình Python ngay, khóa sẽ không hiển thị lại:</p>
    <p class="mt-2 break-all rounded bg-jade-50 p-3 font-mono text-sm"><?= e($newKey['key']) ?></p>
  </div>
<?php endif; ?>
<p class="max-w-3xl text-sm text-ink-soft">Dùng các khóa riêng: một khóa <strong>đọc</strong> (events:read, catalog:read), một khóa <strong>gửi bản nháp</strong> (drafts:write) và, nếu cho AI tự đăng bài, một khóa <strong>xuất bản</strong> (content:publish) dùng riêng. Website chỉ lưu bản băm SHA-256 của khóa. Thu hồi ngay nếu máy cá nhân bị mất.</p>
<div class="mt-4 grid gap-6 xl:grid-cols-[1fr_360px]">
  <div class="a-card overflow-x-auto p-0">
    <table class="a-table">
      <thead><tr><th>Tên</th><th>Tiền tố</th><th>Quyền</th><th>Dùng lần cuối</th><th>Trạng thái</th><th></th></tr></thead>
      <tbody>
      <?php foreach ($keys as $k): ?>
        <tr>
          <td class="font-semibold"><?= e($k['name']) ?></td>
          <td class="font-mono text-xs"><?= e($k['key_prefix']) ?>…</td>
          <td class="text-xs"><?= e(str_replace(',', ', ', $k['scopes'])) ?></td>
          <td class="whitespace-nowrap"><?= $k['last_used_at'] ? vn_time($k['last_used_at']) : 'chưa' ?></td>
          <td><?= $k['is_active'] ? status_badge('active', 'Đang dùng') : status_badge('discontinued', 'Đã thu hồi') ?></td>
          <td><?php if ($k['is_active']): ?><form method="post" action="/admin/api-keys/<?= $k['id'] ?>/revoke" data-confirm="Thu hồi khóa này? Dịch vụ Python dùng khóa sẽ ngừng đồng bộ."><?= csrf_field() ?><button class="text-sm text-alert underline">Thu hồi</button></form><?php endif; ?></td>
        </tr>
      <?php endforeach; ?>
      <?php if (!$keys): ?><tr><td colspan="6" class="py-6 text-center text-ink-mute">Chưa có khóa.</td></tr><?php endif; ?>
      </tbody>
    </table>
  </div>
  <form method="post" action="/admin/api-keys/create" class="a-card h-fit space-y-3"><?= csrf_field() ?>
    <h2 class="text-lg">Tạo khóa</h2>
    <?= a_field('name', 'Tên gợi nhớ', $old['name'] ?? '', $errors, ['attrs' => 'placeholder="python-may-van-phong-doc"']) ?>
    <fieldset><legend class="label">Quyền</legend>
      <?php foreach (['events:read' => 'Đọc sự kiện đơn & bản chụp', 'catalog:read' => 'Đọc thông tin sản phẩm, FAQ', 'drafts:write' => 'Gửi bản nháp, gợi ý, danh sách chăm sóc', 'content:publish' => 'AI tự xuất bản FAQ/blog (trong hạn mức, gỡ được)'] as $s => $l): ?>
        <label class="block text-sm"><input type="checkbox" name="scopes[]" value="<?= $s ?>" class="accent-tea"> <span class="font-mono text-xs"><?= $s ?></span> — <?= $l ?></label>
      <?php endforeach; ?>
      <?php if (!empty($errors['scopes'])): ?><p class="err-msg"><?= e($errors['scopes']) ?></p><?php endif; ?>
    </fieldset>
    <button class="btn-primary w-full">Tạo khóa</button>
  </form>
</div>
