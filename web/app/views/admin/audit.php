<form class="a-card grid gap-3 sm:grid-cols-3 lg:grid-cols-7" method="get">
  <div><label class="label" for="et">Đối tượng</label><select id="et" name="entity_type" class="field"><option value="">Tất cả</option><?php foreach ($types as $t): ?><option <?= ($f['entity_type'] ?? '') === $t ? 'selected' : '' ?>><?= e($t) ?></option><?php endforeach; ?></select></div>
  <div><label class="label" for="eid">Mã đối tượng</label><input id="eid" name="entity_id" value="<?= e($f['entity_id'] ?? '') ?>" class="field"></div>
  <div><label class="label" for="u">Người thao tác</label><select id="u" name="user_id" class="field"><option value="">Tất cả</option><?php foreach ($users as $u): ?><option value="<?= $u['id'] ?>" <?= (int)($f['user_id'] ?? 0) === (int)$u['id'] ? 'selected' : '' ?>><?= e($u['full_name']) ?></option><?php endforeach; ?></select></div>
  <div><label class="label" for="ac">Hành động (tiền tố)</label><input id="ac" name="action" value="<?= e($f['action'] ?? '') ?>" class="field" placeholder="order., refund."></div>
  <div><label class="label" for="from">Từ ngày</label><input id="from" type="date" name="from" value="<?= e($f['from'] ?? '') ?>" class="field"></div>
  <div><label class="label" for="to">Đến ngày</label><input id="to" type="date" name="to" value="<?= e($f['to'] ?? '') ?>" class="field"></div>
  <div class="flex items-end"><button class="btn-primary w-full">Tra cứu</button></div>
</form>
<p class="mt-3 text-sm text-ink-mute"><?= $total ?> bản ghi. Mật khẩu, khóa và thông tin nhận dạng khách được ẩn.</p>
<div class="a-card mt-2 overflow-x-auto p-0">
  <table class="a-table">
    <thead><tr><th>Thời điểm</th><th>Người</th><th>Hành động</th><th>Đối tượng</th><th>Trước → Sau</th><th>Ghi chú</th></tr></thead>
    <tbody>
    <?php foreach ($rows as $a): ?>
      <tr>
        <td class="whitespace-nowrap"><?= vn_time($a['created_at'], 'd/m/Y H:i:s') ?></td>
        <td><?= e($a['full_name'] ?? ($a['actor_type'] === 'sync' ? 'Dịch vụ Python' : 'Hệ thống')) ?><br><span class="text-xs text-ink-mute"><?= e($a['ip']) ?></span></td>
        <td class="font-mono text-xs"><?= e($a['action']) ?></td>
        <td class="text-xs"><?= e($a['entity_type']) ?> #<?= e($a['entity_id']) ?></td>
        <td class="max-w-md text-xs"><?php if ($a['before_json']): ?><span class="text-alert"><?= e(mb_substr($a['before_json'], 0, 300)) ?></span><br><?php endif; ?><?php if ($a['after_json']): ?><span class="text-tea"><?= e(mb_substr($a['after_json'], 0, 300)) ?></span><?php endif; ?></td>
        <td class="text-xs"><?= e($a['note']) ?></td>
      </tr>
    <?php endforeach; ?>
    </tbody>
  </table>
</div>
<?= a_pager($page, $pages, array_intersect_key($f, array_flip(['entity_type', 'entity_id', 'user_id', 'action', 'from', 'to']))) ?>
