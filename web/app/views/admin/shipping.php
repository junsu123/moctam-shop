<p class="max-w-3xl text-sm text-ink-soft">Khách chọn tỉnh/thành ở giỏ hàng; hệ thống tìm vùng chứa tỉnh đó và áp biểu phí đang hiệu lực. Mỗi đơn lưu lại phí tại thời điểm đặt, nên đổi biểu phí không ảnh hưởng đơn cũ.</p>
<div class="mt-4 grid gap-6 xl:grid-cols-[1fr_380px]">
  <div class="space-y-4">
    <?php foreach ($zones as $z): ?>
      <section class="a-card">
        <div class="flex flex-wrap items-center gap-3">
          <h2 class="text-lg"><?= e($z['name']) ?></h2>
          <?= $z['is_active'] ? '' : status_badge('discontinued', 'Tắt') ?>
          <span class="text-sm text-ink-mute"><?= count(json_dec($z['provinces'])) ?> tỉnh/thành, <?= e($z['eta_text']) ?></span>
          <span class="ml-auto font-bold"><?= $z['active'] ? money($z['active']['fee']) . ($z['active']['free_from'] !== null ? ', miễn phí từ ' . money($z['active']['free_from']) : '') : '<span class="text-alert">Chưa có biểu phí hiệu lực</span>' ?></span>
        </div>
        <details class="mt-3">
          <summary class="cursor-pointer text-sm font-semibold text-tea">Sửa vùng và biểu phí</summary>
          <div class="mt-3 grid gap-4 lg:grid-cols-2">
            <form method="post" action="/admin/shipping/zone" class="space-y-3"><?= csrf_field() ?>
              <input type="hidden" name="id" value="<?= $z['id'] ?>">
              <?= a_field('name', 'Tên vùng', $z['name'], []) ?>
              <?= a_field('provinces', 'Tỉnh/thành (mỗi dòng một tên)', implode("\n", json_dec($z['provinces'])), [], ['type' => 'textarea', 'rows' => 6]) ?>
              <?= a_field('eta_text', 'Thời gian giao dự kiến', $z['eta_text'], []) ?>
              <?= a_field('sort_order', 'Thứ tự', $z['sort_order'], [], ['type' => 'number']) ?>
              <?= a_check('is_active', 'Đang phục vụ', (bool)$z['is_active']) ?>
              <button class="btn-ghost w-full">Lưu vùng</button>
            </form>
            <div>
              <form method="post" action="/admin/shipping/rate" class="space-y-3 rounded-lg bg-jade-50 p-3"><?= csrf_field() ?>
                <input type="hidden" name="zone_id" value="<?= $z['id'] ?>">
                <p class="text-sm font-semibold">Biểu phí mới</p>
                <?= a_field('fee', 'Phí giao (₫)', '', [], ['type' => 'number']) ?>
                <?= a_field('free_from', 'Miễn phí khi tiền hàng sau giảm từ (₫, để trống nếu không)', '', [], ['type' => 'number']) ?>
                <?= a_field('effective_from', 'Hiệu lực từ', \App\Core\Clock::toLocalInput(\App\Core\Clock::nowDb()), [], ['type' => 'datetime-local']) ?>
                <button class="btn-primary w-full">Thêm biểu phí</button>
              </form>
              <table class="a-table mt-3 text-xs"><thead><tr><th>Phí</th><th>Miễn phí từ</th><th>Hiệu lực</th></tr></thead><tbody>
                <?php foreach ($z['rates'] as $r): ?><tr class="<?= $z['active'] && $z['active']['id'] === $r['id'] ? 'font-bold' : 'text-ink-mute' ?>"><td><?= money($r['fee']) ?></td><td><?= $r['free_from'] !== null ? money($r['free_from']) : '—' ?></td><td><?= vn_time($r['effective_from']) ?> → <?= $r['effective_to'] ? vn_time($r['effective_to']) : 'nay' ?></td></tr><?php endforeach; ?>
              </tbody></table>
            </div>
          </div>
        </details>
      </section>
    <?php endforeach; ?>
  </div>
  <form method="post" action="/admin/shipping/zone" class="a-card h-fit space-y-3"><?= csrf_field() ?>
    <h2 class="text-lg">Thêm vùng giao</h2>
    <?= a_field('name', 'Tên vùng', $old['name'] ?? '', $errors) ?>
    <?= a_field('provinces', 'Tỉnh/thành (mỗi dòng một tên)', $old['provinces'] ?? '', $errors, ['type' => 'textarea', 'rows' => 5]) ?>
    <?= a_field('eta_text', 'Thời gian giao dự kiến', $old['eta_text'] ?? '', $errors) ?>
    <input type="hidden" name="is_active" value="1">
    <button class="btn-primary w-full">Thêm vùng</button>
  </form>
</div>
