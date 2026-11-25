<?php use App\Domain\ContentService; ?>
<div class="flex flex-wrap items-center gap-2">
  <nav class="flex flex-wrap gap-1 text-sm">
    <a href="?kind=<?= $kind ?>" class="rounded-md px-3 py-1.5 no-underline <?= $st === '' ? 'bg-tea text-white font-semibold' : 'bg-white text-ink' ?>">Tất cả</a>
    <?php foreach (ContentService::STATUS_LABELS as $k => $v): ?>
      <a href="?kind=<?= $kind ?>&status=<?= $k ?>" class="rounded-md px-3 py-1.5 no-underline <?= $st === $k ? 'bg-tea text-white font-semibold' : 'bg-white text-ink' ?>"><?= e($v) ?> <span class="opacity-70"><?= $counts[$k] ?? 0 ?></span></a>
    <?php endforeach; ?>
  </nav>
  <a href="/admin/content/new?kind=<?= $kind ?>" class="btn-primary ml-auto">Tạo <?= e(mb_strtolower(ContentService::KIND_LABELS[$kind])) ?></a>
</div>
<?php if ($kind === 'faq'): ?><p class="mt-3 max-w-3xl text-sm text-ink-soft">Chat tư vấn chỉ dùng FAQ đã xuất bản. Bản nháp do AI soạn luôn ở trạng thái "Chờ duyệt" cho tới khi nhân viên nội dung xuất bản.</p><?php endif; ?>
<div class="a-card mt-4 overflow-x-auto p-0">
  <table class="a-table">
    <thead><tr><th><?= $kind === 'faq' ? 'Câu hỏi' : 'Tiêu đề' ?></th><th>Nguồn</th><th>Phiên bản</th><th>Trạng thái</th><th>Cập nhật</th></tr></thead>
    <tbody>
    <?php foreach ($rows as $c): ?>
      <tr>
        <td><a class="font-semibold" href="/admin/content/<?= $c['id'] ?>"><?= e($c['cur_title']) ?></a>
          <?php if ($c['status'] === 'published' && (int)$c['published_version_id'] !== (int)$c['current_version_id']): ?><br><span class="text-xs text-coffee">Có bản sửa chưa xuất bản</span><?php endif; ?>
          <?php if ($kind !== 'faq'): ?><br><span class="text-xs text-ink-mute">/<?= $kind === 'blog' ? 'blog' : 'chinh-sach' ?>/<?= e($c['slug']) ?></span><?php endif; ?></td>
        <td><?= $c['source'] === 'ai' ? '<span class="badge bg-jade-200 text-tea-dark">AI soạn</span>' : 'Nhân viên' ?></td>
        <td>v<?= (int)$c['version_no'] ?></td>
        <td><?= status_badge($c['status']) ?></td>
        <td class="whitespace-nowrap text-ink-mute"><?= vn_time($c['updated_at']) ?></td>
      </tr>
    <?php endforeach; ?>
    <?php if (!$rows): ?><tr><td colspan="5" class="py-6 text-center text-ink-mute">Chưa có nội dung.</td></tr><?php endif; ?>
    </tbody>
  </table>
</div>
