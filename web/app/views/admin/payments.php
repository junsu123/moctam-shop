<div class="grid gap-6 xl:grid-cols-[1fr_400px]">
  <div class="space-y-6">
    <section class="a-card overflow-x-auto">
      <h2 class="text-lg">Đơn VietQR đang chờ tiền</h2>
      <p class="text-xs text-ink-mute">Khách mở trang QR không có nghĩa là đã chuyển. Chỉ ghi nhận khi thấy giao dịch trên sao kê ngân hàng.</p>
      <table class="a-table mt-3"><thead><tr><th>Mã đơn / nội dung CK</th><th>Khách</th><th class="text-right">Cần thu</th><th class="text-right">Đã nhận</th><th>Hạn giữ hàng</th></tr></thead><tbody>
        <?php foreach ($waiting as $w): ?><tr><td><a class="font-mono font-semibold" href="/admin/orders/<?= $w['id'] ?>"><?= e($w['code']) ?></a></td><td><?= e($w['ship_name']) ?></td><td class="text-right tabular-nums"><?= money($w['total']) ?></td><td class="text-right tabular-nums"><?= money($w['amount_received']) ?></td><td class="whitespace-nowrap <?= $w['expires_at'] < \App\Core\Clock::nowDb() ? 'text-alert font-semibold' : '' ?>"><?= vn_time($w['expires_at']) ?></td></tr><?php endforeach; ?>
        <?php if (!$waiting): ?><tr><td colspan="5" class="text-ink-mute">Không có đơn chờ.</td></tr><?php endif; ?>
      </tbody></table>
    </section>
    <section class="a-card overflow-x-auto">
      <h2 class="text-lg">Khoản thu đã ghi nhận</h2>
      <table class="a-table mt-3"><thead><tr><th>Thời điểm nhận</th><th>Loại</th><th>Nguồn / mã GD</th><th>Đơn</th><th class="text-right">Số tiền</th><th>Người ghi</th></tr></thead><tbody>
        <?php foreach ($rows as $r): ?><tr><td class="whitespace-nowrap"><?= vn_time($r['received_at']) ?></td><td><?= strtoupper(e($r['method'])) ?></td><td><?= e($r['source']) ?><br><span class="font-mono text-xs"><?= e($r['bank_txn_id']) ?></span></td><td><?= $r['code'] ? '<a href="/admin/orders/' . $r['order_id'] . '">' . e($r['code']) . '</a>' : '<span class="text-alert">Chưa khớp</span>' ?></td><td class="text-right font-semibold tabular-nums"><?= money($r['amount']) ?></td><td class="text-xs"><?= e($r['full_name']) ?></td></tr><?php endforeach; ?>
      </tbody></table>
      <?= a_pager($page, $pages, []) ?>
    </section>
  </div>
  <?php if (can('payments.reconcile')): ?>
  <form method="post" action="/admin/payments/vietqr" class="a-card h-fit space-y-3"><?= csrf_field() ?>
    <h2 class="text-lg">Ghi nhận giao dịch VietQR</h2>
    <p class="text-xs text-ink-mute">Nhập theo sao kê. Thiếu/thừa/sai nội dung/sau hạn sẽ tự vào danh sách sai lệch; đơn KHÔNG tự chuyển sang sẵn sàng giao.</p>
    <?= a_field('order_code', 'Mã đơn (để trống để tự dò từ nội dung)', $old['order_code'] ?? '', $errors, ['class' => 'uppercase font-mono']) ?>
    <?= a_field('amount', 'Số tiền (₫)', $old['amount'] ?? '', $errors, ['type' => 'number', 'required' => true]) ?>
    <?= a_field('transfer_content', 'Nội dung chuyển khoản', $old['transfer_content'] ?? '', $errors) ?>
    <?= a_field('source', 'Ngân hàng nhận / nguồn', $old['source'] ?? setting('vietqr_bank_name'), $errors) ?>
    <?= a_field('bank_txn_id', 'Mã giao dịch ngân hàng', $old['bank_txn_id'] ?? '', $errors, ['required' => true, 'hint' => 'Duy nhất theo nguồn — chống ghi trùng.']) ?>
    <?= a_field('received_at', 'Thời điểm tiền về', $old['received_at'] ?? \App\Core\Clock::toLocalInput(\App\Core\Clock::nowDb()), $errors, ['type' => 'datetime-local', 'required' => true]) ?>
    <?= a_field('note', 'Ghi chú', $old['note'] ?? '', $errors) ?>
    <button class="btn-primary w-full">Ghi nhận khoản thu</button>
  </form>
  <?php endif; ?>
</div>
