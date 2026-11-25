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
    ],
    'Hệ thống' => [
        ['/admin/users', 'Tài khoản', 'users.manage', null],
        ['/admin/roles', 'Phân quyền', 'users.manage', null],
        ['/admin/settings', 'Cấu hình', 'settings.manage', null],
        ['/admin/api-keys', 'Khóa API Python', 'settings.manage', null],
        ['/admin/monitor', 'Giám sát', 'audit.view', 'monitor'],
        ['/admin/audit', 'Nhật ký thao tác', 'audit.view', null],
        ['/admin/system/reset', 'Làm mới dữ liệu', 'data.reset', null],
    ],
];
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
<div class="lg:flex">
  <aside class="border-b border-ink/10 bg-ink text-jade-200 lg:sticky lg:top-0 lg:h-screen lg:w-60 lg:shrink-0 lg:overflow-y-auto lg:border-0">
    <div class="flex items-center justify-between px-4 py-4">
      <a href="/admin" class="font-extrabold text-white no-underline"><?= e(setting('store_name')) ?></a>
      <button type="button" class="rounded px-2 py-1 text-sm lg:hidden" data-nav-toggle aria-expanded="false" aria-controls="admin-nav">Menu</button>
    </div>
    <nav id="admin-nav" class="hidden px-2 pb-6 lg:block" aria-label="Quản trị">
      <?php foreach ($nav as $group => $items):
        $visible = array_filter($items, fn($i) => $i[2] === null || can($i[2]));
        if (!$visible) continue; ?>
        <p class="mt-4 px-3 text-xs font-semibold text-jade-300/70"><?= e($group) ?></p>
        <?php foreach ($visible as [$href, $label, $perm, $countKey]):
          $hp = strtok($href, '?');
          $active = $hp === '/admin' ? $path === '/admin' : (str_starts_with($path, $hp) && (!str_contains($href, 'kind=') || str_contains($_SERVER['REQUEST_URI'] ?? '', substr($href, strpos($href, 'kind='))))); ?>
          <a href="<?= e($href) ?>" class="mt-0.5 flex items-center justify-between rounded-md px-3 py-1.5 text-sm no-underline <?= $active ? 'bg-white/10 font-semibold text-white' : 'text-jade-200 hover:bg-white/5 hover:text-white' ?>">
            <span><?= e($label) ?></span>
            <?php if ($countKey && !empty($counts[$countKey])): ?><span class="rounded-full bg-turmeric px-1.5 text-xs font-bold text-ink"><?= (int)$counts[$countKey] ?></span><?php endif; ?>
          </a>
        <?php endforeach; ?>
      <?php endforeach; ?>
    </nav>
  </aside>

  <div class="min-w-0 flex-1">
    <header class="flex items-center justify-between gap-4 border-b border-ink/10 bg-white px-4 py-3 sm:px-6">
      <h1 class="text-lg font-extrabold"><?= e($title ?? 'Quản trị') ?></h1>
      <?php if ($me): ?>
      <div class="flex items-center gap-3 text-sm">
        <a href="/" target="_blank" rel="noopener" class="hidden sm:inline">Xem cửa hàng</a>
        <a href="/admin/account" class="font-semibold text-ink no-underline"><?= e($me['full_name']) ?> <span class="font-normal text-ink-mute">(<?= e($me['role_name']) ?>)</span></a>
        <form method="post" action="/admin/logout"><?= csrf_field() ?><button class="btn-ghost px-3 py-1.5 text-sm">Đăng xuất</button></form>
      </div>
      <?php endif; ?>
    </header>
    <main class="p-4 sm:p-6">
      <?php foreach ($flash as $f): ?>
        <div class="mb-4 rounded-lg px-4 py-3 text-sm font-medium <?= $f['type'] === 'error' ? 'bg-alert-light text-alert' : 'bg-jade-200 text-tea-dark' ?>" role="<?= $f['type'] === 'error' ? 'alert' : 'status' ?>"><?= e($f['msg']) ?></div>
      <?php endforeach; ?>
      <?= $content ?>
    </main>
  </div>
</div>
<script src="<?= asset('js/admin.js') ?>" defer></script>
</body>
</html>
