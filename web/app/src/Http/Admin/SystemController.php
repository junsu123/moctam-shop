<?php
declare(strict_types=1);

namespace App\Http\Admin;

use App\Core\ApiError;
use App\Core\Audit;
use App\Core\Auth;
use App\Core\Clock;
use App\Core\Db;
use App\Core\Session;
use App\Core\Settings;

final class SystemController extends Base
{
    private const SETTING_FIELDS = [
        'Cửa hàng' => [
            'store_name' => 'Tên cửa hàng', 'store_tagline' => 'Khẩu hiệu', 'hotline' => 'Hotline', 'zalo' => 'Số Zalo',
            'support_email' => 'Email hỗ trợ', 'address' => 'Địa chỉ xưởng', 'order_code_prefix' => 'Tiền tố mã đơn (chữ cái)',
        ],
        'Thông tin pháp lý (chân trang, Chính sách bảo mật, Điều khoản sử dụng)' => [
            'business_name' => 'Tên hộ kinh doanh / doanh nghiệp', 'business_reg_no' => 'Số GCN đăng ký kinh doanh / mã số thuế',
            'business_reg_info' => 'Ngày cấp, nơi cấp (VD: cấp ngày 01/02/2026 tại UBND phường …)', 'representative' => 'Người đại diện / chủ hộ',
            'privacy_email' => 'Email liên hệ về dữ liệu cá nhân (để trống = dùng email hỗ trợ)', 'hosting_provider' => 'Nhà cung cấp máy chủ',
            'server_location' => 'Nơi đặt máy chủ (xem trong hPanel, VD: Singapore)', 'complaint_reply_days' => 'Số ngày làm việc phản hồi khiếu nại',
        ],
        'VietQR (tài khoản nhận tiền)' => [
            'vietqr_bank_name' => 'Tên ngân hàng', 'vietqr_bank_bin' => 'Mã BIN ngân hàng (VD Vietcombank 970436)',
            'vietqr_account_no' => 'Số tài khoản', 'vietqr_account_name' => 'Tên chủ tài khoản (không dấu)',
        ],
        'Thời hạn' => [
            'quote_ttl_minutes' => 'Hiệu lực báo giá (phút)', 'hold_hours_vietqr' => 'Giữ hàng chờ VietQR (giờ)', 'hold_hours_cod' => 'Chờ xác nhận COD (giờ)',
        ],
        'Chat & dữ liệu' => [
            'chat_faq_threshold' => 'Ngưỡng khớp FAQ của chat (0–1, hiệu chỉnh bằng lệnh Python "calibrate")',
            'chat_log_days' => 'Giữ câu hỏi chat (ngày)', 'sync_event_retention_days' => 'Giữ sự kiện đồng bộ (ngày)',
        ],
    ];

    // ------------------------------------------------------------ tài khoản
    public function users(): string
    {
        $this->need('users.manage');
        return $this->view('users', [
            'title' => 'Tài khoản nhân viên',
            'users' => Db::all('SELECT u.*, r.name AS role_name FROM users u JOIN roles r ON r.code = u.role_code ORDER BY u.is_active DESC, u.full_name'),
            'roles' => Db::all('SELECT * FROM roles ORDER BY name'),
        ]);
    }

    public function saveUser(): void
    {
        $this->need('users.manage');
        $id = $this->int('id');
        $email = mb_strtolower($this->str('email'));
        $extra = array_values(array_intersect(array_keys(Auth::PERMISSIONS), (array)($_POST['extra'] ?? [])));
        $data = ['full_name' => mb_substr($this->str('full_name'), 0, 120), 'role_code' => $this->str('role_code'), 'is_active' => $this->str('is_active') ? 1 : 0,
            'extra_permissions' => json_enc($extra), 'updated_at' => Clock::nowDb()];
        $err = [];
        if (!filter_var($email, FILTER_VALIDATE_EMAIL)) $err['email'] = 'Email không hợp lệ';
        if ($data['full_name'] === '') $err['full_name'] = 'Bắt buộc';
        if (!Db::val('SELECT 1 FROM roles WHERE code = :c', ['c' => $data['role_code']])) $err['role_code'] = 'Chọn vai trò';
        $pass = (string)($_POST['password'] ?? '');
        if ((!$id || $pass !== '') && strlen($pass) < 10) $err['password'] = 'Mật khẩu tối thiểu 10 ký tự';
        if ($id === Auth::id() && (!$data['is_active'] || $data['role_code'] !== Auth::user()['role_code'])) $err['role_code'] = 'Không thể tự khóa hoặc đổi vai trò của chính mình';
        if ($err) throw ApiError::validation($err);
        if ($pass !== '') $data['password_hash'] = password_hash($pass, PASSWORD_DEFAULT);
        try {
            if ($id) {
                $before = Db::one('SELECT email, full_name, role_code, is_active, extra_permissions FROM users WHERE id = :id', ['id' => $id]);
                Db::update('users', $data + ['email' => $email], 'id = :id', ['id' => $id]);
                Audit::log('user.update', 'user', (string)$id, $before, array_diff_key($data, ['password_hash' => 1]) + ['password_changed' => $pass !== '']);
            } else {
                $id = Db::insert('users', $data + ['email' => $email, 'created_at' => Clock::nowDb()]);
                Audit::log('user.create', 'user', (string)$id, null, array_diff_key($data, ['password_hash' => 1]) + ['email' => $email]);
            }
        } catch (\PDOException $e) {
            if (Db::isDuplicate($e)) throw ApiError::validation(['email' => 'Email đã được dùng']);
            throw $e;
        }
        $this->back('Đã lưu tài khoản.');
    }

    /** Mở khóa tài khoản nhân viên bị tạm khóa do nhập sai mật khẩu nhiều lần. */
    public function unlockUser(string $id): void
    {
        $this->need('users.manage');
        Auth::unlock((int)$id);
        $this->back('Đã mở khóa đăng nhập.');
    }

    public function roles(): string
    {
        $this->need('users.manage');
        return $this->view('roles', ['title' => 'Phân quyền', 'roles' => Db::all('SELECT r.*, (SELECT COUNT(*) FROM users u WHERE u.role_code = r.code AND u.is_active = 1) AS n FROM roles r ORDER BY r.code = "admin" DESC, r.name')]);
    }

    public function saveRole(): void
    {
        $this->need('users.manage');
        $code = $this->str('code');
        if ($code === 'admin') throw new ApiError('FORBIDDEN', 'Không sửa quyền của vai trò Quản trị viên.', 403);
        $perms = array_values(array_intersect(array_keys(Auth::PERMISSIONS), (array)($_POST['perms'] ?? [])));
        $name = mb_substr($this->str('name'), 0, 100);
        $before = Db::one('SELECT * FROM roles WHERE code = :c', ['c' => $code]);
        if ($before) {
            Db::update('roles', ['name' => $name ?: $before['name'], 'permissions' => json_enc($perms)], 'code = :c', ['c' => $code]);
        } else {
            $code = preg_replace('/[^a-z0-9_]/', '', strtolower($code)) ?: 'role_' . substr(bin2hex(random_bytes(2)), 0, 4);
            Db::insert('roles', ['code' => $code, 'name' => $name ?: $code, 'permissions' => json_enc($perms)]);
        }
        Audit::log('role.save', 'role', $code, $before ? ['permissions' => json_dec($before['permissions'])] : null, ['permissions' => $perms]);
        $this->back('Đã lưu phân quyền.');
    }

    // ------------------------------------------------------------ cấu hình
    public function settings(): string
    {
        $this->need('settings.manage');
        return $this->view('settings', ['title' => 'Cấu hình', 'groups' => self::SETTING_FIELDS, 'values' => Settings::all()]);
    }

    public function saveSettings(): void
    {
        $this->need('settings.manage');
        $before = Settings::all();
        $changed = [];
        $err = [];
        foreach (self::SETTING_FIELDS as $fields) {
            foreach ($fields as $k => $_) {
                if (!array_key_exists($k, $_POST)) continue;
                $v = trim((string)$_POST[$k]);
                if (in_array($k, ['quote_ttl_minutes', 'hold_hours_vietqr', 'hold_hours_cod', 'chat_log_days', 'sync_event_retention_days', 'complaint_reply_days'], true) && (!ctype_digit($v) || (int)$v < 1)) $err[$k] = 'Nhập số nguyên dương';
                if ($k === 'chat_faq_threshold' && (!is_numeric($v) || $v < 0 || $v > 1)) $err[$k] = 'Từ 0 đến 1';
                if ($k === 'privacy_email' && $v !== '' && !filter_var($v, FILTER_VALIDATE_EMAIL)) $err[$k] = 'Email không hợp lệ';
                if ($k === 'vietqr_bank_bin' && !preg_match('/^\d{6}$/', $v)) $err[$k] = 'Mã BIN gồm 6 chữ số';
                if ($k === 'vietqr_account_no' && !preg_match('/^[0-9A-Za-z]{4,19}$/', $v)) $err[$k] = 'Số tài khoản 4–19 ký tự';
                if (($before[$k] ?? null) !== $v) $changed[$k] = $v;
            }
        }
        if ($err) throw ApiError::validation($err);
        foreach ($changed as $k => $v) Settings::set($k, $v);
        Audit::log('settings.update', 'settings', 'global', array_intersect_key($before, $changed), $changed);
        $this->back($changed ? 'Đã lưu ' . count($changed) . ' thay đổi.' : 'Không có thay đổi.');
    }

    // ------------------------------------------------------------ khóa API
    public function apiKeys(): string
    {
        $this->need('settings.manage');
        $new = $_SESSION['new_api_key'] ?? null;
        unset($_SESSION['new_api_key']);
        return $this->view('api_keys', ['title' => 'Khóa API cho dịch vụ Python', 'keys' => Db::all('SELECT * FROM api_keys ORDER BY is_active DESC, id DESC'), 'newKey' => $new]);
    }

    public function createKey(): void
    {
        $this->need('settings.manage');
        $scopes = array_values(array_intersect(['events:read', 'catalog:read', 'drafts:write'], (array)($_POST['scopes'] ?? [])));
        $name = mb_substr($this->str('name'), 0, 100);
        if (!$scopes || $name === '') throw ApiError::validation(['name' => $name === '' ? 'Bắt buộc' : null, 'scopes' => !$scopes ? 'Chọn ít nhất một quyền' : null]);
        $key = 'xk_' . bin2hex(random_bytes(24));
        $id = Db::insert('api_keys', ['name' => $name, 'key_prefix' => substr($key, 0, 8), 'key_hash' => hash('sha256', $key), 'scopes' => implode(',', $scopes), 'created_at' => Clock::nowDb()]);
        Audit::log('apikey.create', 'api_key', (string)$id, null, ['name' => $name, 'scopes' => $scopes]);
        $_SESSION['new_api_key'] = ['name' => $name, 'key' => $key];
        $this->back('Đã tạo khóa — sao chép ngay, khóa chỉ hiển thị một lần.', '/admin/api-keys');
    }

    public function revokeKey(string $id): void
    {
        $this->need('settings.manage');
        Db::exec('UPDATE api_keys SET is_active = 0 WHERE id = :id', ['id' => (int)$id]);
        Audit::log('apikey.revoke', 'api_key', $id);
        $this->back('Đã thu hồi khóa.');
    }

    // ------------------------------------------------------------ nhật ký
    public function audit(): string
    {
        $this->need('audit.view');
        $where = ['1=1'];
        $p = [];
        if (($et = $this->str('entity_type')) !== '') { $where[] = 'a.entity_type = :et'; $p['et'] = $et; }
        if (($eid = $this->str('entity_id')) !== '') { $where[] = 'a.entity_id = :eid'; $p['eid'] = $eid; }
        if ($uid = $this->int('user_id')) { $where[] = 'a.user_id = :u'; $p['u'] = $uid; }
        if (($ac = $this->str('action')) !== '') { $where[] = 'a.action LIKE :ac'; $p['ac'] = $ac . '%'; }
        if ($from = Clock::fromLocalInput($this->str('from') ? $this->str('from') . 'T00:00' : '')) { $where[] = 'a.created_at >= :f'; $p['f'] = $from; }
        if ($to = Clock::fromLocalInput($this->str('to') ? $this->str('to') . 'T23:59:59' : '')) { $where[] = 'a.created_at <= :t'; $p['t'] = $to; }
        $page = max(1, $this->int('page', 1));
        $total = (int)Db::val('SELECT COUNT(*) FROM audit_logs a WHERE ' . implode(' AND ', $where), $p);
        $rows = Db::all('SELECT a.*, u.full_name FROM audit_logs a LEFT JOIN users u ON u.id = a.user_id WHERE ' . implode(' AND ', $where) . ' ORDER BY a.id DESC LIMIT 50 OFFSET :o', $p + ['o' => ($page - 1) * 50]);
        return $this->view('audit', [
            'title' => 'Nhật ký thao tác', 'rows' => $rows, 'f' => $_GET, 'page' => $page, 'pages' => (int)ceil($total / 50), 'total' => $total,
            'users' => Db::all('SELECT id, full_name FROM users ORDER BY full_name'),
            'types' => array_column(Db::all('SELECT DISTINCT entity_type FROM audit_logs ORDER BY entity_type'), 'entity_type'),
        ]);
    }

    // ------------------------------------------------------------ tài khoản của tôi
    public function account(): string
    {
        return $this->view('account', ['title' => 'Tài khoản của tôi']);
    }

    public function changePassword(): void
    {
        $u = Db::one('SELECT password_hash FROM users WHERE id = :id', ['id' => Auth::id()]);
        if (!password_verify((string)($_POST['current'] ?? ''), $u['password_hash'])) throw ApiError::validation(['current' => 'Mật khẩu hiện tại không đúng']);
        $new = (string)($_POST['new'] ?? '');
        if (strlen($new) < 10) throw ApiError::validation(['new' => 'Tối thiểu 10 ký tự']);
        Db::update('users', ['password_hash' => password_hash($new, PASSWORD_DEFAULT), 'updated_at' => Clock::nowDb()], 'id = :id', ['id' => Auth::id()]);
        Audit::log('user.password', 'user', (string)Auth::id());
        Session::regenerate();
        $this->back('Đã đổi mật khẩu.');
    }
}
