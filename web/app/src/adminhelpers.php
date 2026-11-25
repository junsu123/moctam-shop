<?php
declare(strict_types=1);

/** Trợ giúp hiển thị cho trang quản trị. */

use App\Core\Auth;

function can(string $perm): bool
{
    return Auth::can($perm);
}

/** Ô nhập có nhãn + lỗi cạnh trường. $opts: type, required, options(assoc), rows, hint, attrs, class */
function a_field(string $name, string $label, mixed $value, array $errors = [], array $opts = []): string
{
    $id = 'f_' . preg_replace('/[^a-z0-9_]/i', '_', $name);
    $type = $opts['type'] ?? 'text';
    $err = $errors[$name] ?? null;
    $cls = 'field' . ($err ? ' field-error' : '') . (isset($opts['class']) ? ' ' . $opts['class'] : '');
    $attrs = ($opts['required'] ?? false ? ' required' : '') . ($err ? ' aria-invalid="true" aria-describedby="' . $id . '_e"' : '') . ' ' . ($opts['attrs'] ?? '');
    $html = '<div class="' . e($opts['wrap'] ?? '') . '"><label for="' . $id . '" class="label">' . e($label) . '</label>';
    if ($type === 'select') {
        $html .= '<select id="' . $id . '" name="' . e($name) . '" class="' . $cls . '"' . $attrs . '>';
        foreach ($opts['options'] ?? [] as $k => $v) {
            $html .= '<option value="' . e($k) . '"' . ((string)$k === (string)$value ? ' selected' : '') . '>' . e($v) . '</option>';
        }
        $html .= '</select>';
    } elseif ($type === 'textarea') {
        $html .= '<textarea id="' . $id . '" name="' . e($name) . '" rows="' . (int)($opts['rows'] ?? 4) . '" class="' . $cls . '"' . $attrs . '>' . e($value) . '</textarea>';
    } else {
        $html .= '<input id="' . $id . '" type="' . e($type) . '" name="' . e($name) . '" value="' . e($value) . '" class="' . $cls . '"' . $attrs . '>';
    }
    if (!empty($opts['hint'])) $html .= '<p class="mt-1 text-xs text-ink-mute">' . e($opts['hint']) . '</p>';
    if ($err) $html .= '<p id="' . $id . '_e" class="err-msg">' . e($err) . '</p>';
    return $html . '</div>';
}

function a_check(string $name, string $label, bool $checked): string
{
    return '<label class="inline-flex items-center gap-2 text-sm font-medium"><input type="checkbox" name="' . e($name) . '" value="1" class="h-4 w-4 accent-tea"' . ($checked ? ' checked' : '') . '> ' . e($label) . '</label>';
}

function status_badge(string $status, ?string $label = null): string
{
    $map = [
        'pending' => 'bg-turmeric-light text-coffee', 'confirmed' => 'bg-jade-200 text-tea-dark', 'shipping' => 'bg-blue-100 text-blue-800',
        'delivered' => 'bg-tea text-white', 'cancelled' => 'bg-ink/10 text-ink-soft', 'returning' => 'bg-orange-100 text-orange-800', 'returned' => 'bg-ink/10 text-ink',
        'unpaid' => 'bg-ink/5 text-ink-soft', 'partial' => 'bg-alert-light text-alert', 'paid' => 'bg-jade-200 text-tea-dark', 'overpaid' => 'bg-turmeric-light text-coffee',
        'partially_refunded' => 'bg-orange-100 text-orange-800', 'refunded' => 'bg-ink/10 text-ink',
        'draft' => 'bg-ink/5 text-ink-soft', 'pending_review' => 'bg-turmeric-light text-coffee', 'published' => 'bg-jade-200 text-tea-dark', 'unpublished' => 'bg-ink/10 text-ink-soft',
        'open' => 'bg-alert-light text-alert', 'resolved' => 'bg-jade-200 text-tea-dark', 'completed' => 'bg-jade-200 text-tea-dark',
        'active' => 'bg-jade-200 text-tea-dark', 'discontinued' => 'bg-ink/10 text-ink-soft', 'approved' => 'bg-jade-200 text-tea-dark', 'rejected' => 'bg-ink/10 text-ink-soft',
        'contacted' => 'bg-jade-200 text-tea-dark', 'skipped' => 'bg-ink/10 text-ink-soft', 'ok' => 'bg-jade-200 text-tea-dark', 'failed' => 'bg-alert-light text-alert',
    ];
    $labels = \App\Domain\OrderService::STATUS_LABELS + \App\Domain\OrderService::PAYMENT_LABELS + \App\Domain\ContentService::STATUS_LABELS + [
        'open' => 'Đang mở', 'resolved' => 'Đã xử lý', 'completed' => 'Đã hoàn', 'active' => 'Đang bán', 'discontinued' => 'Ngừng bán',
        'approved' => 'Đã duyệt', 'rejected' => 'Từ chối', 'contacted' => 'Đã liên hệ', 'skipped' => 'Bỏ qua', 'ok' => 'OK', 'failed' => 'Lỗi',
    ];
    return '<span class="badge ' . ($map[$status] ?? 'bg-ink/5 text-ink') . '">' . e($label ?? $labels[$status] ?? $status) . '</span>';
}

function a_pager(int $page, int $pages, array $query): string
{
    if ($pages <= 1) return '';
    $path = strtok($_SERVER['REQUEST_URI'] ?? '', '?');
    $link = fn(int $n, string $label, string $aria = '') => '<a class="rounded-md border border-ink/10 bg-white px-3 py-1.5 no-underline hover:bg-jade-200"' . ($aria ? ' aria-label="' . $aria . '"' : '') . ' href="' . e(url($path, ['page' => $n] + $query)) . '">' . $label . '</a>';
    $h = '<nav class="mt-4 flex flex-wrap items-center gap-1 text-sm" aria-label="Phân trang">';
    if ($page > 1) $h .= $link($page - 1, '‹ Trước', 'Trang trước');
    for ($i = max(1, $page - 3); $i <= min($pages, $page + 3); $i++) {
        $h .= $i === $page ? '<span class="rounded-md bg-tea px-3 py-1.5 font-bold text-white" aria-current="page">' . $i . '</span>' : $link($i, (string)$i);
    }
    if ($page < $pages) $h .= $link($page + 1, 'Sau ›', 'Trang sau');
    return $h . '<span class="ml-2 text-ink-mute">Trang ' . $page . '/' . $pages . '</span></nav>';
}
