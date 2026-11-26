<section class="wrap py-12">
  <div class="mx-auto max-w-lg">
    <h1 class="text-3xl">Trạng thái xóa dữ liệu</h1>
    <?php if (!$row): ?>
      <p class="mt-4 rounded-xl bg-white p-5 text-ink-soft">Không tìm thấy mã xác nhận <?= $code !== '' ? '<strong class="font-mono">' . e($code) . '</strong>' : '' ?>. Kiểm tra lại mã hoặc liên hệ hotline <?= e(setting('hotline')) ?>.</p>
    <?php else: ?>
      <div class="mt-4 rounded-xl bg-white p-5">
        <p>Mã xác nhận: <strong class="font-mono"><?= e($row['confirmation_code']) ?></strong></p>
        <p class="mt-1">Thời điểm yêu cầu: <?= vn_time($row['requested_at']) ?></p>
        <p class="mt-3 font-semibold text-tea-dark"><?= $row['status'] === 'completed'
            ? 'Đã xóa tài khoản và dữ liệu đăng nhập nhận từ ' . ($row['source'] === 'facebook' ? 'Facebook' : 'nhà cung cấp đăng nhập') . '.'
            : 'Không có tài khoản nào gắn với yêu cầu này — xưởng không lưu dữ liệu đăng nhập của bạn.' ?></p>
        <p class="mt-3 text-sm text-ink-soft">Thông tin trên các đơn đã đặt được lưu theo thời hạn pháp luật về kế toán, thuế yêu cầu. Xem <a href="<?= page_url('bao-mat') ?>">Chính sách bảo mật thông tin</a>.</p>
      </div>
    <?php endif; ?>
  </div>
</section>
