<section class="wrap py-12">
  <div class="mx-auto max-w-md">
    <h1 class="text-3xl">Đăng nhập</h1>
    <p class="mt-2 text-ink-soft">Không bắt buộc — bạn vẫn có thể <a href="/gio-hang">đặt hàng không cần tài khoản</a>. Đăng nhập để xem lại đơn đã đặt và không phải nhập lại địa chỉ.</p>

    <?php foreach ($notices as $f): ?>
      <p class="mt-4 rounded-lg px-3 py-2 text-sm <?= $f['type'] === 'error' ? 'bg-alert-light text-alert' : 'bg-jade-200 text-tea-dark' ?>" role="<?= $f['type'] === 'error' ? 'alert' : 'status' ?>"><?= e($f['msg']) ?></p>
    <?php endforeach; ?>

    <?php if (!$providers): ?>
      <p class="mt-6 rounded-xl bg-white p-5 text-ink-soft">Xưởng chưa bật đăng nhập. Bạn vẫn đặt hàng bình thường; mỗi đơn có đường dẫn riêng để xem lại.</p>
    <?php else: ?>
      <div class="mt-6 space-y-3">
        <?php if (in_array('google', $providers, true)): ?>
          <a href="/auth/google?next=<?= e(rawurlencode($next)) ?>" class="btn w-full border border-ink/20 bg-white py-3 text-ink hover:bg-jade-50">Tiếp tục với Google</a>
        <?php endif; ?>
        <?php if (in_array('facebook', $providers, true)): ?>
          <a href="/auth/facebook?next=<?= e(rawurlencode($next)) ?>" class="btn w-full bg-[#1877F2] py-3 text-white hover:bg-[#166fe0]">Tiếp tục với Facebook</a>
        <?php endif; ?>
      </div>
      <p class="mt-6 text-xs leading-relaxed text-ink-mute">Xưởng chỉ nhận tên, email và mã định danh tài khoản từ nhà cung cấp, không đăng bài hay đọc danh sách bạn bè của bạn. Khi tiếp tục, bạn đồng ý với <a href="/chinh-sach/dieu-khoan-su-dung">Điều khoản sử dụng</a> và <a href="/chinh-sach/bao-mat">Chính sách bảo mật thông tin</a>.</p>
    <?php endif; ?>
  </div>
</section>
