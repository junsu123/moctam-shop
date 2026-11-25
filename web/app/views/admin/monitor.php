<?php $levelCls = ['ok' => 'bg-tea', 'warn' => 'bg-turmeric', 'bad' => 'bg-alert']; ?>
<div class="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
  <?php foreach ($health as $h): ?>
    <div class="a-card">
      <p class="flex items-center gap-2 text-sm text-ink-soft"><span class="h-2.5 w-2.5 rounded-full <?= $levelCls[$h['level']] ?>"></span><?= e($h['name']) ?></p>
      <p class="mt-1 font-bold"><?= e($h['value']) ?></p>
      <?php if (!empty($h['note'])): ?><p class="mt-1 text-xs text-ink-mute"><?= e($h['note']) ?></p><?php endif; ?>
    </div>
  <?php endforeach; ?>
</div>

<div class="mt-6 grid gap-6 xl:grid-cols-2">
  <section class="a-card overflow-x-auto">
    <h2 class="text-lg">Tác vụ nền gần đây</h2>
    <table class="a-table mt-3"><thead><tr><th>Tác vụ</th><th>Kết quả</th><th>Chi tiết</th><th>Lúc chạy</th></tr></thead><tbody>
      <?php foreach ($jobs as $j): ?><tr><td><?= e($j['job']) ?></td><td><?= status_badge($j['status']) ?></td><td class="max-w-xs truncate text-xs text-ink-mute" title="<?= e($j['detail']) ?>"><?= e($j['detail']) ?></td><td class="whitespace-nowrap"><?= vn_time($j['started_at']) ?></td></tr><?php endforeach; ?>
      <?php if (!$jobs): ?><tr><td colspan="4" class="text-ink-mute">Chưa có tác vụ nào chạy. Đặt Cron cho bin/cron.php (5 phút) và bin/backup.php (hằng ngày).</td></tr><?php endif; ?>
    </tbody></table>
  </section>
  <section class="a-card">
    <h2 class="text-lg">Chat 7 ngày qua</h2>
    <ul class="mt-3 flex flex-wrap gap-4 text-sm">
      <?php $srcLabel = ['faq' => 'Trả lời bằng FAQ', 'live' => 'Dữ liệu giá/tồn/ưu đãi', 'label' => 'Thông tin nhãn', 'fallback' => 'Chuyển kênh hỗ trợ']; foreach ($chat as $c): ?>
        <li><span class="text-2xl font-extrabold tabular-nums"><?= (int)$c['n'] ?></span><br><span class="text-ink-mute"><?= e($srcLabel[$c['source']] ?? $c['source']) ?></span></li>
      <?php endforeach; ?>
    </ul>
    <h3 class="mt-5 font-semibold">Câu hỏi chưa có câu trả lời (30 ngày)</h3>
    <p class="text-xs text-ink-mute">Dịch vụ Python dùng danh sách này để đề xuất FAQ mới.</p>
    <ul class="mt-2 space-y-1 text-sm">
      <?php foreach ($unanswered as $u): ?><li class="flex justify-between gap-3"><span><?= e($u['question']) ?></span><span class="text-ink-mute"><?= (int)$u['n'] ?></span></li><?php endforeach; ?>
    </ul>
  </section>
</div>

<section class="a-card mt-6 overflow-x-auto">
  <h2 class="text-lg">Lỗi vận hành gần đây</h2>
  <p class="text-xs text-ink-mute">Đã loại bỏ số điện thoại và khóa API khỏi nội dung lỗi.</p>
  <table class="a-table mt-3"><thead><tr><th>Kênh</th><th>Mã</th><th>Nội dung</th><th>Lúc</th></tr></thead><tbody>
    <?php foreach ($errors as $er): ?><tr><td><?= e($er['channel']) ?></td><td class="font-mono text-xs"><?= e($er['code']) ?></td><td class="text-xs"><?= e($er['message']) ?></td><td class="whitespace-nowrap"><?= vn_time($er['created_at']) ?></td></tr><?php endforeach; ?>
    <?php if (!$errors): ?><tr><td colspan="4" class="text-ink-mute">Không có lỗi.</td></tr><?php endif; ?>
  </tbody></table>
</section>
