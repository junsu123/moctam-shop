<form method="post" action="/admin/settings" class="max-w-4xl space-y-6"><?= csrf_field() ?>
  <?php foreach ($groups as $g => $fields): ?>
    <section class="a-card">
      <h2 class="text-lg"><?= e($g) ?></h2>
      <div class="mt-3 grid gap-4 sm:grid-cols-2">
        <?php foreach ($fields as $k => $label): ?><?= a_field($k, $label, $old[$k] ?? ($values[$k] ?? ''), $errors) ?><?php endforeach; ?>
      </div>
      <?php if (str_starts_with($g, 'Thời hạn')): ?><p class="mt-3 text-xs text-ink-mute">Giá trị khởi điểm theo đặc tả: 15 phút báo giá, 24 giờ VietQR, 48 giờ COD. Xưởng chốt theo lịch trực đối soát và tốc độ giao hàng.</p><?php endif; ?>
    </section>
  <?php endforeach; ?>
  <button class="btn-primary">Lưu cấu hình</button>
</form>
