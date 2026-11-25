<!doctype html>
<html lang="vi">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Đăng nhập quản trị — <?= e(setting('store_name')) ?></title>
<meta name="robots" content="noindex">
<link rel="stylesheet" href="<?= asset('css/app.css') ?>">
</head>
<body class="flex min-h-screen items-center justify-center bg-ink p-4">
  <form method="post" action="/admin/login" class="w-full max-w-sm rounded-2xl bg-white p-7">
    <?= csrf_field() ?>
    <p class="text-sm font-semibold text-tea"><?= e(setting('store_name')) ?></p>
    <h1 class="mt-1 text-2xl">Đăng nhập quản trị</h1>
    <?php foreach ($flash as $f): ?><p class="mt-4 rounded-lg bg-alert-light px-3 py-2 text-sm text-alert" role="alert"><?= e($f['msg']) ?></p><?php endforeach; ?>
    <div class="mt-5 space-y-4">
      <div><label for="email" class="label">Email</label><input id="email" name="email" type="email" value="<?= e($email) ?>" class="field" autocomplete="username" required autofocus></div>
      <div><label for="password" class="label">Mật khẩu</label><input id="password" name="password" type="password" class="field" autocomplete="current-password" required></div>
    </div>
    <button class="btn-primary mt-6 w-full">Đăng nhập</button>
  </form>
</body>
</html>
