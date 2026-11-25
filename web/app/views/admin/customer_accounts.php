<?php
use App\Core\Text;
use App\Domain\CustomerAccountService as Accounts;

$cur = $f['status'] ?? '';
$tabs = ['' => ['Tất cả', $stats['total'] ?? 0], 'active' => ['Đang hoạt động', ($stats['total'] ?? 0) - ($stats['locked'] ?? 0)], 'locked' => ['Đang khóa', $stats['locked'] ?? 0]];
?>
<p class="max-w-3xl text-sm text-ink-soft">Tài khoản khách tạo khi đăng nhập bằng Google hoặc Facebook (không bắt buộc để mua hàng). Website không lưu mật khẩu của khách: mỗi tài khoản đăng nhập qua một hoặc nhiều nhà cung cấp bên dưới. Trong 30 ngày qua có <?= (int)($stats['active30'] ?? 0) ?> tài khoản đăng nhập.</p>

<nav class="mt-4 flex flex-wrap gap-1 text-sm" aria-label="Lọc theo trạng thái">
  <?php foreach ($tabs as $k => [$label, $n]): ?>
    <a href="<?= e(url('/admin/customer-accounts', array_filter(['status' => $k, 'q' => $f['q'] ?? '', 'provider' => $f['provider'] ?? '']))) ?>" class="rounded-md px-3 py-1.5 no-underline <?= $cur === $k ? 'bg-tea text-white font-semibold' : 'bg-white text-ink hover:bg-jade-200' ?>"><?= e($label) ?> <span class="<?= $cur === $k ? 'text-jade-200' : 'text-ink-mute' ?>"><?= (int)$n ?></span></a>
  <?php endforeach; ?>
</nav>

<form class="a-card mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-6" method="get">
  <input type="hidden" name="status" value="<?= e($cur) ?>">
  <div class="lg:col-span-3"><label class="label" for="q">Email, tên, SĐT giao hàng hoặc mã tài khoản</label><input id="q" name="q" value="<?= e($f['q'] ?? '') ?>" class="field"></div>
  <div><label class="label" for="provider">Đăng nhập bằng</label><select id="provider" name="provider" class="field"><option value="">Tất cả</option><?php foreach (Accounts::PROVIDER_LABELS as $k => $v): ?><option value="<?= $k ?>" <?= ($f['provider'] ?? '') === $k ? 'selected' : '' ?>><?= e($v) ?></option><?php endforeach; ?></select></div>
  <div class="flex items-end gap-2 lg:col-span-2"><button class="btn-primary">Lọc</button><a href="/admin/customer-accounts" class="btn-ghost">Xóa lọc</a><span class="ml-auto self-center text-sm text-ink-mute"><?= (int)$total ?> tài khoản</span></div>
</form>

<div class="a-card mt-4 overflow-x-auto p-0">
  <table class="a-table">
    <thead><tr><th>Tài khoản</th><th>Email</th><th>Đăng nhập bằng</th><th>SĐT giao hàng</th><th class="text-right">Đơn</th><th>Đăng nhập gần nhất</th><th>Tạo lúc</th><th>Trạng thái</th></tr></thead>
    <tbody>
    <?php foreach ($rows as $r): ?>
      <tr>
        <td><a href="/admin/customer-accounts/<?= (int)$r['id'] ?>" class="font-semibold"><?= e($r['display_name']) ?></a><br><span class="text-xs text-ink-mute">#<?= (int)$r['id'] ?></span></td>
        <td><?= $r['email'] ? e($r['email']) : '<span class="text-ink-mute">không có</span>' ?></td>
        <td><?php foreach (array_filter(explode(',', (string)$r['providers'])) as $pv): ?><span class="badge bg-jade-200 text-tea-dark"><?= e(Accounts::PROVIDER_LABELS[$pv] ?? $pv) ?></span> <?php endforeach; ?></td>
        <td class="whitespace-nowrap"><?= $r['ship_phone'] ? e(Text::maskPhone($r['ship_phone'])) : '' ?></td>
        <td class="text-right tabular-nums"><?= (int)$r['order_count'] ?></td>
        <td class="whitespace-nowrap"><?= $r['last_login_at'] ? vn_time($r['last_login_at']) : 'chưa' ?></td>
        <td class="whitespace-nowrap"><?= vn_time($r['created_at'], 'd/m/Y') ?></td>
        <td><?= $r['locked_at'] ? status_badge('failed', 'Đang khóa') : status_badge('active', 'Hoạt động') ?></td>
      </tr>
    <?php endforeach; ?>
    <?php if (!$rows): ?><tr><td colspan="8" class="text-ink-mute"><?= ($stats['total'] ?? 0) ? 'Không có tài khoản khớp bộ lọc.' : 'Chưa có khách nào đăng nhập. Nút đăng nhập chỉ hiện khi đã cấu hình Google/Facebook (docs/TRIEN-KHAI-HOSTINGER.md §10).' ?></td></tr><?php endif; ?>
    </tbody>
  </table>
</div>
<?= a_pager($page, $pages, array_filter(['status' => $cur, 'q' => $f['q'] ?? '', 'provider' => $f['provider'] ?? ''])) ?>
