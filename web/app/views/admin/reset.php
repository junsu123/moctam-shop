<?php use App\Domain\DataResetService; ?>
<div class="max-w-4xl space-y-6">
  <div class="rounded-lg border-2 border-alert/40 bg-alert-light p-4 text-sm text-alert" role="alert">
    <p class="font-bold">Thao tác này xóa vĩnh viễn dữ liệu thử và không hoàn tác được trên giao diện.</p>
    <p class="mt-1">Hệ thống tự sao lưu toàn bộ CSDL và ảnh <strong>trước khi xóa</strong>; nếu sao lưu lỗi sẽ dừng, không xóa gì. Khôi phục theo docs/SAO-LUU-KHOI-PHUC.md nếu cần.</p>
    <?php if ($lastReset): ?><p class="mt-1">Lần làm mới gần nhất: <?= vn_time($lastReset) ?>.</p><?php endif; ?>
  </div>

  <form method="get" class="a-card">
    <h2 class="text-lg">1. Chọn phạm vi</h2>
    <p class="mt-1 text-sm text-ink-soft">Luôn xóa: đơn, khách, khoản thu, sai lệch, hoàn tiền, lượt voucher đã dùng, danh sách chăm sóc, gợi ý/nội dung AI chưa xuất bản, biến động kho, sự kiện đồng bộ. Luôn giữ: cấu hình, vai trò, tài khoản quản trị, danh mục, vùng giao & phí, trang chính sách.</p>
    <div class="mt-4 space-y-2">
      <?php foreach (DataResetService::OPTIONS as $k => $label): ?>
        <label class="flex items-start gap-2 text-sm"><input type="checkbox" name="<?= $k ?>" value="1" class="mt-0.5 h-4 w-4 accent-tea" <?= $opts[$k] ? 'checked' : '' ?> data-autosubmit> <span><?= e($label) ?><?php if ($k === 'demo_users' && $meIsDemo): ?> <span class="text-coffee">(trừ tài khoản bạn đang dùng — hãy tạo tài khoản quản trị thật trước)</span><?php endif; ?></span></label>
      <?php endforeach; ?>
    </div>
    <noscript><button class="btn-ghost mt-3">Cập nhật xem trước</button></noscript>
  </form>

  <section class="a-card">
    <h2 class="text-lg">2. Xem trước</h2>
    <table class="a-table mt-3 max-w-md">
      <tbody>
      <?php foreach ($preview as $label => $n): ?>
        <tr><td><?= e($label) ?></td><td class="text-right font-bold tabular-nums <?= $n > 0 ? 'text-alert' : 'text-ink-mute' ?>"><?= number_format($n, 0, ',', '.') ?></td></tr>
      <?php endforeach; ?>
      </tbody>
    </table>
  </section>

  <form method="post" action="/admin/system/reset" class="a-card space-y-4" data-confirm="Xóa vĩnh viễn dữ liệu đã chọn? Hệ thống sẽ sao lưu trước khi xóa."><?= csrf_field() ?>
    <h2 class="text-lg">3. Xác nhận</h2>
    <?php foreach ($opts as $k => $v): if ($v): ?><input type="hidden" name="<?= $k ?>" value="1"><?php endif; endforeach; ?>
    <div class="grid gap-4 sm:grid-cols-2">
      <?= a_field('confirm', 'Gõ "' . DataResetService::CONFIRM_PHRASE . '"', '', $errors, ['attrs' => 'autocomplete="off" spellcheck="false"']) ?>
      <?= a_field('password', 'Mật khẩu của bạn', '', $errors, ['type' => 'password', 'attrs' => 'autocomplete="current-password"']) ?>
    </div>
    <button class="btn bg-alert text-white hover:bg-alert/90">Sao lưu rồi làm mới dữ liệu</button>
    <p class="text-xs text-ink-mute">Sau khi làm mới: dịch vụ Python tự tải lại dữ liệu ở lần đồng bộ tới. Nếu đã thu hồi khóa API, tạo khóa mới và cập nhật config.toml.</p>
  </form>
</div>
