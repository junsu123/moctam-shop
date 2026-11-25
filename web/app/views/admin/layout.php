<?php
$path = strtok($_SERVER['REQUEST_URI'] ?? '/admin', '?');
$counts = $me ? \App\Http\Admin\DashboardController::navCounts() : [];
$nav = [
    'Vận hành' => [
        ['/admin', 'Tổng quan', null, null],
        ['/admin/orders', 'Đơn hàng', 'orders.view', 'orders'],
        ['/admin/inventory', 'Tồn kho', 'inventory.manage', null],
        ['/admin/products', 'Sản phẩm', 'catalog.manage', null],
        ['/admin/categories', 'Danh mục', 'catalog.manage', null],
        ['/admin/shipping', 'Vùng giao & phí', 'shipping.manage', null],
    ],
    'Ưu đãi' => [
        ['/admin/vouchers', 'Voucher', 'promo.manage', null],
        ['/admin/flash-sales', 'Flash Sale', 'promo.manage', null],
        ['/admin/crosssell', 'Gợi ý mua kèm', 'crosssell.review', 'crosssell'],
    ],
    'Tài chính' => [
        ['/admin/payments', 'Khoản thu', 'payments.view', null],
        ['/admin/discrepancies', 'Sai lệch', 'payments.reconcile', 'discrepancies'],
        ['/admin/refunds', 'Hoàn tiền', 'payments.view', 'refunds'],
    ],
    'Nội dung & khách' => [
        ['/admin/content?kind=blog', 'Blog', 'content.edit', null],
        ['/admin/content?kind=faq', 'FAQ', 'content.edit', 'faq_review'],
        ['/admin/content?kind=page', 'Trang chính sách', 'content.edit', null],
        ['/admin/care', 'Chăm sóc lại', 'care.view', 'care'],
        ['/admin/customer-accounts', 'Tài khoản khách', 'accounts.manage', null],
    ],
    'Hệ thống' => [
        ['/admin/users', 'Tài khoản nhân viên', 'users.manage', null],
        ['/admin/roles', 'Phân quyền', 'users.manage', null],
        ['/admin/settings', 'Cấu hình', 'settings.manage', null],
        ['/admin/api-keys', 'Khóa API Python', 'settings.manage', null],
        ['/admin/monitor', 'Giám sát', 'audit.view', 'monitor'],
        ['/admin/audit', 'Nhật ký thao tác', 'audit.view', null],
        ['/admin/system/reset', 'Làm mới dữ liệu', 'data.reset', null],
    ],
];
// Nhóm menu đang gập (cookie do admin.js ghi) — nhóm chứa trang hiện tại luôn mở
$closed = array_filter(explode(',', (string)($_COOKIE['a_nav'] ?? '')));
$groupKey = fn(string $g) => substr(md5($g), 0, 6);
$isActive = function (string $href) use ($path): bool {
    $hp = strtok($href, '?');
    if ($hp === '/admin') return $path === '/admin';
    if (!str_starts_with($path, $hp)) return false;
    return !str_contains($href, 'kind=') || str_contains($_SERVER['REQUEST_URI'] ?? '', substr($href, strpos($href, 'kind=')));
};
$showRole = $me && $me['role_name'] !== $me['full_name'];
?><!doctype html>
<html lang="vi">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title><?= e($title ?? 'Quản trị') ?> — <?= e(setting('store_name')) ?></title>
<meta name="robots" content="noindex">
<link rel="stylesheet" href="<?= asset('css/app.css') ?>">
<link rel="icon" href="/assets/img/favicon.svg" type="image/svg+xml">
</head>
<body class="bg-jade-50">
<a href="#main" class="sr-only focus:not-sr-only focus:fixed focus:left-3 focus:top-3 focus:z-50 focus:rounded-md focus:bg-white focus:px-4 focus:py-2 focus:font-semibold">Bỏ qua menu</a>
<div class="lg:flex">
  <aside class="bg-ink text-jade-200 lg:sticky lg:top-0 lg:flex lg:h-screen lg:w-60 lg:shrink-0 lg:flex-col">
    <div class="flex items-center justify-between px-4 py-3.5">
      <a href="/admin" class="font-extrabold text-white no-underline"><?= e(setting('store_name')) ?></a>
      <button type="button" class="rounded-md border border-white/20 px-3 py-1 text-sm text-white lg:hidden" data-nav-toggle aria-expanded="false" aria-controls="admin-nav">Menu<?php if ($counts && array_sum($counts)): ?> <span class="ml-1 rounded-full bg-turmeric px-1.5 text-xs font-bold text-ink"><?= (int)array_sum($counts) ?></span><?php endif; ?></button>
    </div>
    <nav id="admin-nav" class="hidden min-h-0 flex-1 overflow-y-auto px-2 pb-4 lg:block" aria-label="Quản trị">
      <?php foreach ($nav as $group => $items):
        $visible = array_filter($items, fn($i) => $i[2] === null || can($i[2]));
        if (!$visible) continue;
        $key = $groupKey($group);
        $hasActive = (bool)array_filter($visible, fn($i) => $isActive($i[0]));
        $groupCount = array_sum(array_map(fn($i) => $i[3] ? (int)($counts[$i[3]] ?? 0) : 0, $visible)); ?>
        <details class="group mt-2" data-navgroup="<?= $key ?>" <?= $hasActive || !in_array($key, $closed, true) ? 'open' : '' ?>>
          <summary class="flex cursor-pointer list-none items-center gap-2 rounded-md px-3 py-1.5 text-xs font-semibold text-jade-300 hover:text-white [&::-webkit-details-marker]:hidden">
            <svg class="h-3 w-3 shrink-0 transition-transform group-open:rotate-90" viewBox="0 0 12 12" aria-hidden="true"><path d="M4 2l4 4-4 4" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>
            <span><?= e($group) ?></span>
            <?php if ($groupCount): ?><span class="ml-auto rounded-full bg-turmeric px-1.5 text-xs font-bold text-ink group-open:hidden"><?= $groupCount ?></span><?php endif; ?>
          </summary>
          <?php foreach ($visible as [$href, $label, $perm, $countKey]): $active = $isActive($href); ?>
            <a href="<?= e($href) ?>" <?= $active ? 'aria-current="page"' : '' ?> class="flex items-center justify-between rounded-md px-3 py-1.5 pl-8 text-sm no-underline <?= $active ? 'bg-white/10 font-semibold text-white shadow-[inset_3px_0_0_#D9A21B]' : 'text-jade-200 hover:bg-white/5 hover:text-white' ?>">
              <span><?= e($label) ?></span>
              <?php if ($countKey && !empty($counts[$countKey])): ?><span class="rounded-full bg-turmeric px-1.5 text-xs font-bold text-ink"><?= (int)$counts[$countKey] ?></span><?php endif; ?>
            </a>
          <?php endforeach; ?>
        </details>
      <?php endforeach; ?>
      <?php if ($me): ?>
      <div class="mt-4 border-t border-white/10 px-3 pt-4 text-sm lg:hidden">
        <a href="/admin/account" class="block font-semibold text-white no-underline"><?= e($me['full_name']) ?></a>
        <?php if ($showRole): ?><span class="text-jade-300"><?= e($me['role_name']) ?></span><?php endif; ?>
        <div class="mt-3 flex gap-2">
          <a href="/" target="_blank" rel="noopener" class="rounded-md border border-white/20 px-3 py-1.5 text-jade-200 no-underline">Xem cửa hàng</a>
          <form method="post" action="/admin/logout"><?= csrf_field() ?><button class="rounded-md border border-white/20 px-3 py-1.5 text-jade-200">Đăng xuất</button></form>
        </div>
      </div>
      <?php endif; ?>
    </nav>
  </aside>

  <div class="min-w-0 flex-1">
    <header class="sticky top-0 z-20 border-b border-ink/10 bg-white/95 backdrop-blur">
      <div class="flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-2.5 sm:px-6">
        <h1 class="min-w-0 flex-1 truncate text-lg font-extrabold"><?= e($title ?? 'Quản trị') ?></h1>
        <?php if ($me && can('orders.view')): ?>
        <form action="/admin/orders" method="get" role="search" class="order-last w-full sm:order-none sm:w-72">
          <input type="hidden" name="go" value="1">
          <label for="quick-q" class="sr-only">Tìm đơn theo mã, số điện thoại hoặc mã vận đơn</label>
          <div class="relative">
            <svg class="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-mute" viewBox="0 0 20 20" aria-hidden="true"><circle cx="8.5" cy="8.5" r="5.5" fill="none" stroke="currentColor" stroke-width="2"/><path d="M13 13l4 4" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>
            <input id="quick-q" name="q" type="search" autocomplete="off" placeholder="Tìm đơn: mã, SĐT, vận đơn" class="field py-2 pl-9 pr-8 text-sm" data-quick-search>
            <kbd class="pointer-events-none absolute right-2.5 top-1/2 hidden -translate-y-1/2 rounded border border-ink/20 px-1.5 text-xs text-ink-mute sm:block" title="Nhấn / để tìm">/</kbd>
          </div>
        </form>
        <?php endif; ?>
        <?php if ($me): ?>
        <div class="hidden items-center gap-3 text-sm lg:flex">
          <a href="/" target="_blank" rel="noopener" class="text-ink-soft">Xem cửa hàng</a>
          <a href="/admin/account" class="text-right leading-tight text-ink no-underline" title="Tài khoản của tôi"><span class="block font-semibold"><?= e($me['full_name']) ?></span><?php if ($showRole): ?><span class="block text-xs text-ink-mute"><?= e($me['role_name']) ?></span><?php endif; ?></a>
          <form method="post" action="/admin/logout"><?= csrf_field() ?><button class="btn-ghost px-3 py-1.5 text-sm">Đăng xuất</button></form>
        </div>
        <?php endif; ?>
      </div>
    </header>
    <main id="main" tabindex="-1" class="p-4 focus:outline-none sm:p-6">
      <?php foreach ($flash as $f): $isErr = $f['type'] === 'error'; ?>
        <div class="mb-4 flex items-start gap-3 rounded-lg border px-4 py-3 text-sm font-medium <?= $isErr ? 'border-alert/30 bg-alert-light text-alert' : 'border-tea/20 bg-jade-200 text-tea-dark' ?>" role="<?= $isErr ? 'alert' : 'status' ?>" data-flash>
          <span class="flex-1"><?= e($f['msg']) ?></span>
          <button type="button" class="-my-1 rounded px-2 text-lg leading-none opacity-70 hover:opacity-100" data-dismiss aria-label="Đóng thông báo">×</button>
        </div>
      <?php endforeach; ?>
      <?= $content ?>
    </main>
  </div>
</div>
<script src="<?= asset('js/admin.js') ?>" defer></script>
</body>
</html>
