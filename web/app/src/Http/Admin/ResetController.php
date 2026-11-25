<?php
declare(strict_types=1);

namespace App\Http\Admin;

use App\Core\ApiError;
use App\Core\Auth;
use App\Core\Db;
use App\Core\Settings;
use App\Domain\DataResetService;

/** Quản trị → Làm mới dữ liệu (chỉ Quản trị viên). */
final class ResetController extends Base
{
    public function form(): string
    {
        $this->need('data.reset');
        $opts = DataResetService::normalize($_GET);
        return $this->view('reset', [
            'title' => 'Làm mới dữ liệu trước khi chạy thật',
            'opts' => $opts,
            'preview' => DataResetService::preview($opts),
            'lastReset' => Settings::get('data_reset_at'),
            'demoUsers' => (int)Db::val("SELECT COUNT(*) FROM users WHERE email LIKE '%@xuong.local'"),
            'meIsDemo' => str_ends_with((string)Auth::user()['email'], '@xuong.local'),
        ]);
    }

    public function run(): void
    {
        $this->need('data.reset');
        $err = [];
        if ($this->str('confirm') !== DataResetService::CONFIRM_PHRASE) {
            $err['confirm'] = 'Gõ chính xác "' . DataResetService::CONFIRM_PHRASE . '"';
        }
        $hash = Db::val('SELECT password_hash FROM users WHERE id = :id', ['id' => Auth::id()]);
        if (!password_verify((string)($_POST['password'] ?? ''), (string)$hash)) {
            $err['password'] = 'Mật khẩu không đúng';
        }
        if ($err) throw ApiError::validation($err, 'Chưa làm mới dữ liệu: cần xác nhận.');
        $r = DataResetService::run($_POST, Auth::id());
        $n = array_sum($r['deleted']);
        $this->back('Đã làm mới dữ liệu (' . $n . ' bản ghi). Bản sao lưu trước khi xóa: ' . basename((string)($r['backup']['file'] ?? '')) . '.', '/admin/system/reset');
    }
}
