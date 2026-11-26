<?php
use App\Domain\ContentService;
$val = fn($k, $d = '') => $old[$k] ?? ($cur[$k] ?? $d);
$refs = $cur ? json_dec($cur['source_refs'] ?? '') : [];
$outdated = [];
foreach ($refs as $r) {
    if (is_array($r) && isset($r['product_id'], $r['info_version'])) {
        foreach ($products as $p) if ((int)$p['id'] === (int)$r['product_id'] && (int)$p['info_version'] !== (int)$r['info_version']) $outdated[] = $p['name'];
    }
}
?>
<a href="/admin/content?kind=<?= e($kind) ?>" class="text-sm">← <?= e(ContentService::KIND_LABELS[$kind]) ?></a>
<?php if ($c): ?>
  <div class="mt-2 flex flex-wrap items-center gap-2 text-sm"><?= status_badge($c['status']) ?> <?= $c['source'] === 'ai' ? '<span class="badge bg-jade-200 text-tea-dark">AI soạn — cần kiểm tra số liệu, thành phần, giá</span>' : '' ?>
    <?php if ($c['status'] === 'published' && $kind !== 'faq'): ?><a href="<?= e(page_url($c['slug'])) ?>" target="_blank" rel="noopener">Xem bản công khai</a><?php endif; ?></div>
<?php endif; ?>
<?php if ($outdated): ?><div class="mt-3 rounded-lg bg-alert-light p-3 text-sm text-alert" role="alert">Thông tin nhãn của <?= e(implode(', ', $outdated)) ?> đã thay đổi sau khi bản này được soạn. Kiểm tra lại trước khi xuất bản.</div><?php endif; ?>

<div class="mt-3 grid gap-6 xl:grid-cols-[1fr_340px]">
  <form method="post" action="/admin/content/save" class="a-card space-y-4"><?= csrf_field() ?>
    <input type="hidden" name="id" value="<?= (int)($c['id'] ?? 0) ?>">
    <input type="hidden" name="kind" value="<?= e($kind) ?>">
    <?= a_field('title', $kind === 'faq' ? 'Câu hỏi' : 'Tiêu đề', $val('title'), $errors) ?>
    <?php if ($kind !== 'faq'): ?>
      <?= a_field('meta_description', 'Mô tả SEO (≤ 160 ký tự)', $val('meta_description'), $errors, ['attrs' => 'maxlength="320"']) ?>
      <?php if (!$c || !$c['published_version_id']): ?>
        <?= a_field('slug', 'Đường dẫn', $old['slug'] ?? ($c['slug'] ?? ''), $errors, ['hint' => 'Để trống sẽ tạo từ tiêu đề. Cố định sau lần xuất bản đầu tiên.']) ?>
      <?php else: ?>
        <p class="text-sm text-ink-mute">Đường dẫn cố định: <?= e(page_url($c['slug'])) ?></p>
      <?php endif; ?>
    <?php endif; ?>
    <?= a_field('body', $kind === 'faq' ? 'Câu trả lời (HTML cơ bản)' : 'Nội dung (HTML cơ bản: p, h2, h3, ul, ol, strong, a, img, table)', $val('body'), $errors, ['type' => 'textarea', 'rows' => 16, 'class' => 'font-mono text-sm']) ?>
    <div class="grid gap-4 sm:grid-cols-3">
      <?= a_field('keywords', 'Từ khóa (giúp chat tìm FAQ)', $val('keywords'), $errors) ?>
      <?= a_field('category_id', 'Danh mục liên quan', $old['category_id'] ?? ($c['category_id'] ?? ''), $errors, ['type' => 'select', 'options' => ['' => '—'] + array_column($cats, 'name', 'id')]) ?>
      <?= a_field('product_id', 'Sản phẩm liên quan', $old['product_id'] ?? ($c['product_id'] ?? ''), $errors, ['type' => 'select', 'options' => ['' => '—'] + array_column($products, 'name', 'id')]) ?>
    </div>
    <div class="flex flex-wrap gap-2 border-t border-ink/10 pt-4">
      <button name="action" value="save" class="btn-ghost">Lưu bản nháp</button>
      <button name="action" value="submit" class="btn-ghost">Lưu & gửi duyệt</button>
      <?php if (can('content.publish')): ?><button name="action" value="publish" class="btn-primary">Lưu & xuất bản</button><?php endif; ?>
    </div>
  </form>

  <aside class="space-y-6">
    <?php if ($c && can('content.publish')): ?>
    <section class="a-card space-y-3">
      <h2 class="text-lg">Duyệt</h2>
      <form method="post" action="/admin/content/<?= $c['id'] ?>/publish"><?= csrf_field() ?><input type="hidden" name="version_id" value="<?= (int)($cur['id'] ?? 0) ?>">
        <?= a_field('note', 'Ghi chú duyệt', '', []) ?>
        <button class="btn-primary mt-2 w-full">Xuất bản phiên bản v<?= (int)($cur['version_no'] ?? 0) ?></button></form>
      <?php if ($c['status'] === 'pending_review'): ?>
      <form method="post" action="/admin/content/<?= $c['id'] ?>/reject"><?= csrf_field() ?><?= a_field('note', 'Lý do trả về', '', []) ?><button class="btn-ghost mt-2 w-full">Trả về</button></form>
      <?php endif; ?>
      <?php if ($c['status'] === 'published'): ?>
      <form method="post" action="/admin/content/<?= $c['id'] ?>/unpublish" data-confirm="Gỡ nội dung khỏi website?"><?= csrf_field() ?><input type="hidden" name="reason" value="Gỡ thủ công"><button class="w-full text-sm font-semibold text-alert underline">Gỡ khỏi website</button></form>
      <?php endif; ?>
    </section>
    <?php endif; ?>
    <?php if ($versions): ?>
    <section class="a-card">
      <h2 class="text-lg">Lịch sử phiên bản</h2>
      <ol class="mt-3 space-y-2 text-sm">
        <?php foreach ($versions as $v): ?>
          <li class="<?= (int)$v['id'] === (int)($cur['id'] ?? 0) ? 'font-semibold' : '' ?>">
            <a href="?version=<?= $v['id'] ?>">v<?= (int)$v['version_no'] ?></a>
            <?= (int)$v['id'] === (int)$c['published_version_id'] ? '<span class="badge bg-jade-200 text-tea-dark">đang công khai</span>' : '' ?>
            <span class="text-ink-mute">— <?= vn_time($v['created_at']) ?>, <?= $v['created_source'] === 'ai' ? 'AI' : e($v['full_name'] ?? '') ?></span>
            <?php if ($v['review_note']): ?><br><span class="text-xs text-ink-soft"><?= e($v['review_note']) ?><?= $v['reviewer'] ? ' (' . e($v['reviewer']) . ')' : '' ?></span><?php endif; ?>
          </li>
        <?php endforeach; ?>
      </ol>
      <?php if ($refs): ?><p class="mt-3 text-xs text-ink-mute">Nguồn tham chiếu: <?= e(json_enc($refs)) ?></p><?php endif; ?>
    </section>
    <?php endif; ?>
  </aside>
</div>
