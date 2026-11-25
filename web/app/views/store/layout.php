<?php
/** @var string $content */
$store = setting('store_name');
if (!isset($categories)) { try { $categories = \App\Domain\CatalogService::categories(); } catch (\Throwable) { $categories = []; } }
$pageTitle = $title ?? $store;
$metaDesc = $description ?? setting('store_tagline');
$canonical = rtrim((string)config('base_url'), '/') . strtok($_SERVER['REQUEST_URI'] ?? '/', '?');
?><!doctype html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title><?= e($pageTitle) ?></title>
<meta name="description" content="<?= e($metaDesc) ?>">
<?php if (!empty($robots)): ?><meta name="robots" content="<?= e($robots) ?>"><?php endif; ?>
<link rel="canonical" href="<?= e($canonical) ?>">
<meta property="og:title" content="<?= e($pageTitle) ?>">
<meta property="og:description" content="<?= e($metaDesc) ?>">
<meta property="og:type" content="<?= e($ogType ?? 'website') ?>">
<?php if (!empty($ogImage)): ?><meta property="og:image" content="<?= e(rtrim((string)config('base_url'), '/') . $ogImage) ?>"><?php endif; ?>
<meta name="csrf-token" content="<?= e(\App\Core\Csrf::token()) ?>">
<link rel="preload" href="/assets/fonts/be-vietnam-pro-vietnamese-400-normal.woff2" as="font" type="font/woff2" crossorigin>
<link rel="stylesheet" href="<?= asset('css/app.css') ?>">
<link rel="icon" href="/assets/img/favicon.svg" type="image/svg+xml">
</head>
<body class="min-h-screen flex flex-col">
<a href="#noi-dung" class="sr-only focus:not-sr-only focus:absolute focus:left-3 focus:top-3 focus:z-50 btn-primary">Bỏ qua tới nội dung</a>

<header class="sticky top-0 z-30 border-b border-ink/10 bg-jade-100/95 backdrop-blur">
  <div class="wrap flex items-center gap-3 py-3 sm:gap-6">
    <a href="/" class="flex shrink-0 items-center gap-2 no-underline" aria-label="<?= e($store) ?> — trang chủ">
      <svg width="34" height="34" viewBox="0 0 40 40" aria-hidden="true"><rect width="40" height="40" rx="9" fill="#2F5D46"/><path d="M20 8c7 4 9 12 2 22-1 1-3 1-4 0C11 20 13 12 20 8z" fill="#E9EFE6"/><path d="M20 12v18" stroke="#2F5D46" stroke-width="2"/></svg>
      <span class="text-lg font-extrabold tracking-tight text-ink"><?= e($store) ?></span>
    </a>
    <form action="/tim-kiem" method="get" role="search" class="relative hidden flex-1 md:block">
      <label for="q-top" class="sr-only">Tìm sản phẩm</label>
      <input id="q-top" name="q" value="<?= e($q ?? '') ?>" class="field pr-10" placeholder="Tìm trà gừng, matcha, CF-ROB…" autocomplete="off" data-autocomplete>
      <button class="absolute right-2 top-1/2 -translate-y-1/2 rounded p-1.5 text-ink-soft hover:text-tea" aria-label="Tìm"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg></button>
      <div class="absolute left-0 right-0 top-full z-40 mt-1 hidden rounded-lg border border-ink/10 bg-white shadow-lg" data-autocomplete-list></div>
    </form>
    <nav class="ml-auto flex items-center gap-1" aria-label="Tài khoản và giỏ hàng">
      <a href="/tim-kiem" class="rounded-lg p-2 text-ink md:hidden" aria-label="Tìm kiếm"><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg></a>
      <a href="/gio-hang" class="relative flex items-center gap-2 rounded-lg px-3 py-2 font-semibold text-ink no-underline hover:bg-white/70">
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M5 7h14l-1.5 10.5a2 2 0 0 1-2 1.5h-7a2 2 0 0 1-2-1.5L5 7z"/><path d="M9 7V5a3 3 0 0 1 6 0v2"/></svg>
        <span class="hidden sm:inline">Giỏ hàng</span>
        <span class="min-w-[1.4rem] rounded-full bg-tea px-1.5 text-center text-xs font-bold leading-6 text-white" data-cart-count aria-label="Số sản phẩm trong giỏ">0</span>
      </a>
    </nav>
  </div>
  <nav class="wrap flex gap-1 overflow-x-auto pb-2 text-sm" aria-label="Danh mục">
    <?php foreach ($categories as $c): ?>
      <a href="/danh-muc/<?= e($c['slug']) ?>" class="whitespace-nowrap rounded-md px-3 py-1.5 font-medium no-underline <?= ($activeCat ?? 0) === (int)$c['id'] ? 'bg-tea text-white' : 'text-ink-soft hover:bg-white/70 hover:text-ink' ?>"><?= e($c['name']) ?></a>
    <?php endforeach; ?>
    <a href="/flash-sale" class="whitespace-nowrap rounded-md px-3 py-1.5 font-semibold text-turmeric-dark no-underline hover:bg-turmeric-light">Flash Sale</a>
    <a href="/blog" class="whitespace-nowrap rounded-md px-3 py-1.5 font-medium text-ink-soft no-underline hover:bg-white/70">Blog</a>
    <a href="/hoi-dap" class="whitespace-nowrap rounded-md px-3 py-1.5 font-medium text-ink-soft no-underline hover:bg-white/70">Hỏi đáp</a>
  </nav>
</header>

<main id="noi-dung" class="flex-1"><?= $content ?></main>

<footer class="mt-16 bg-ink text-jade-200">
  <div class="wrap grid gap-8 py-12 sm:grid-cols-2 lg:grid-cols-4">
    <div>
      <p class="text-lg font-extrabold text-white"><?= e($store) ?></p>
      <p class="mt-2 text-sm leading-relaxed"><?= e(setting('store_tagline')) ?></p>
      <p class="mt-3 text-sm"><?= e(setting('address')) ?></p>
    </div>
    <div>
      <p class="font-semibold text-white">Liên hệ</p>
      <ul class="mt-2 space-y-1 text-sm">
        <li>Hotline: <a class="text-jade-100" href="tel:<?= e(preg_replace('/\s/', '', setting('hotline'))) ?>"><?= e(setting('hotline')) ?></a></li>
        <li>Zalo: <a class="text-jade-100" href="https://zalo.me/<?= e(setting('zalo')) ?>" rel="noopener"><?= e(setting('zalo')) ?></a></li>
        <li>Email: <a class="text-jade-100" href="mailto:<?= e(setting('support_email')) ?>"><?= e(setting('support_email')) ?></a></li>
      </ul>
    </div>
    <div>
      <p class="font-semibold text-white">Chính sách</p>
      <ul class="mt-2 space-y-1 text-sm">
        <li><a class="text-jade-100" href="/chinh-sach/giao-hang">Giao hàng</a></li>
        <li><a class="text-jade-100" href="/chinh-sach/thanh-toan">Thanh toán</a></li>
        <li><a class="text-jade-100" href="/chinh-sach/doi-tra">Đổi trả</a></li>
        <li><a class="text-jade-100" href="/chinh-sach/bao-mat">Bảo mật thông tin</a></li>
        <li><a class="text-jade-100" href="/chinh-sach/dieu-khoan-su-dung">Điều khoản sử dụng</a></li>
        <li><a class="text-jade-100" href="/chinh-sach/lien-he">Liên hệ</a></li>
      </ul>
    </div>
    <div>
      <p class="font-semibold text-white">Thanh toán</p>
      <p class="mt-2 text-sm">Thanh toán khi nhận hàng (COD) hoặc chuyển khoản VietQR. Đặt hàng không cần tạo tài khoản.</p>
    </div>
  </div>
  <div class="wrap space-y-1 border-t border-white/10 py-4 text-xs text-jade-300">
    <?php if (setting('business_name') !== '' || setting('business_reg_no') !== ''): ?>
      <p><?= e(setting('business_name') ?: $store) ?><?= setting('business_reg_no') !== '' ? ' — GCN ĐKKD/MST: ' . e(setting('business_reg_no')) : '' ?><?= setting('business_reg_info') !== '' ? ', ' . e(setting('business_reg_info')) : '' ?><?= setting('representative') !== '' ? '. Người đại diện: ' . e(setting('representative')) : '' ?></p>
    <?php endif; ?>
    <p>© <?= date('Y') ?> <?= e($store) ?></p>
  </div>
</footer>

<!-- Chat tư vấn -->
<div class="fixed bottom-4 right-4 z-40" data-chat>
  <button type="button" class="flex items-center gap-2 rounded-full bg-tea p-3.5 sm:px-4 sm:py-3 font-semibold text-white shadow-lg hover:bg-tea-dark" data-chat-toggle aria-expanded="false" aria-controls="chat-panel">
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M4 5h16v11H8l-4 4z"/></svg>
    <span class="hidden sm:inline">Hỏi xưởng</span><span class="sr-only sm:hidden">Hỏi xưởng</span>
  </button>
  <section id="chat-panel" class="absolute bottom-16 right-0 hidden w-[min(92vw,380px)] overflow-hidden rounded-2xl border border-ink/10 bg-white shadow-2xl" aria-label="Chat tư vấn" data-chat-panel>
    <header class="flex items-center justify-between bg-tea px-4 py-3 text-white">
      <p class="font-semibold">Tư vấn sản phẩm</p>
      <button type="button" class="rounded p-1 hover:bg-white/10" data-chat-toggle aria-label="Đóng chat">✕</button>
    </header>
    <div class="h-80 space-y-3 overflow-y-auto bg-jade-50 p-4 text-sm" data-chat-log aria-live="polite">
      <div class="max-w-[85%] rounded-xl rounded-tl-sm bg-white p-3 shadow-sm">Chào bạn! Hỏi mình về giá, tình trạng hàng, ưu đãi, thành phần hay cách pha nhé.</div>
    </div>
    <form class="flex gap-2 border-t border-ink/10 p-3" data-chat-form>
      <label for="chat-input" class="sr-only">Câu hỏi</label>
      <input id="chat-input" class="field py-2" maxlength="500" placeholder="VD: Matcha còn hàng không?" autocomplete="off" required>
      <button class="btn-primary px-4 py-2">Gửi</button>
    </form>
  </section>
</div>

<div class="pointer-events-none fixed inset-x-0 bottom-20 z-50 flex justify-center px-4" aria-live="polite" data-toast></div>
<script src="<?= asset('js/app.js') ?>" defer></script>
</body>
</html>
