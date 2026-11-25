<?php
declare(strict_types=1);

namespace App\Core;

/**
 * Đăng nhập nhân viên và kiểm tra quyền trên TỪNG thao tác tại máy chủ (NFR-01, AT-07).
 */
final class Auth
{
    public const PERMISSIONS = [
        'catalog.manage'     => 'Quản lý danh mục, sản phẩm, quy cách',
        'inventory.manage'   => 'Điều chỉnh, nhập kho',
        'shipping.manage'    => 'Quản lý vùng giao và biểu phí',
        'promo.manage'       => 'Quản lý voucher, Flash Sale',
        'orders.view'        => 'Xem đơn hàng',
        'orders.process'     => 'Xác nhận, bàn giao, giao thành công, hủy đơn',
        'orders.return'      => 'Ghi nhận hàng trả, kiểm hàng',
        'payments.view'      => 'Xem lịch sử tài chính của đơn',
        'payments.reconcile' => 'Ghi nhận khoản thu, xử lý sai lệch',
        'refunds.approve'    => 'Duyệt và ghi nhận hoàn tiền',
        'content.edit'       => 'Soạn blog, FAQ, trang',
        'content.publish'    => 'Duyệt và xuất bản/gỡ nội dung',
        'crosssell.review'   => 'Duyệt gợi ý mua kèm',
        'care.view'          => 'Xem danh sách chăm sóc lại',
        'users.manage'       => 'Quản lý tài khoản và phân quyền',
        'settings.manage'    => 'Cấu hình hệ thống, khóa API',
        'audit.view'         => 'Xem nhật ký thao tác và giám sát',
    ];

    private static ?array $user = null;
    private static bool $loaded = false;

    public static function user(): ?array
    {
        if (!self::$loaded) {
            self::$loaded = true;
            $id = $_SESSION['admin_uid'] ?? null;
            if ($id) {
                $idle = (int)config('session.admin_idle_minutes', 60) * 60;
                if (time() - (int)($_SESSION['admin_seen'] ?? 0) > $idle) {
                    self::logout();
                    return null;
                }
                $_SESSION['admin_seen'] = time();
                $u = Db::one('SELECT u.*, r.permissions AS role_permissions, r.name AS role_name FROM users u JOIN roles r ON r.code = u.role_code WHERE u.id = :id AND u.is_active = 1', ['id' => $id]);
                if ($u) {
                    $u['perms'] = array_values(array_unique(array_merge(json_dec($u['role_permissions']), json_dec($u['extra_permissions']))));
                    unset($u['password_hash']);
                    self::$user = $u;
                }
            }
        }
        return self::$user;
    }

    /** Dùng trong kiểm thử / CLI. */
    public static function actAs(?int $userId): void
    {
        $_SESSION['admin_uid'] = $userId;
        $_SESSION['admin_seen'] = time();
        self::$loaded = false;
        self::$user = null;
    }

    public static function id(): ?int
    {
        return self::user()['id'] ?? null;
    }

    public static function can(string $perm): bool
    {
        $u = self::user();
        if (!$u) {
            return false;
        }
        return in_array('*', $u['perms'], true) || in_array($perm, $u['perms'], true);
    }

    public static function require(string $perm): void
    {
        if (!self::user()) {
            throw new ApiError('UNAUTHENTICATED', 'Vui lòng đăng nhập.', 401);
        }
        if (!self::can($perm)) {
            Audit::log('permission_denied', 'permission', $perm, null, null, 'Từ chối: thiếu quyền ' . $perm);
            throw ApiError::forbidden();
        }
    }

    public static function attempt(string $email, string $password): bool
    {
        $u = Db::one('SELECT * FROM users WHERE email = :e', ['e' => mb_strtolower(trim($email))]);
        $now = Clock::now();
        if (!$u || !$u['is_active']) {
            password_verify($password, '$2y$10$usesomesillystringfore7hnbRJHxXVLeakoG8K30oukPsA.ztMG'); // cân bằng thời gian
            return false;
        }
        if ($u['locked_until'] && $u['locked_until'] > Clock::nowDb()) {
            return false;
        }
        if (!password_verify($password, $u['password_hash'])) {
            $fails = (int)$u['failed_logins'] + 1;
            Db::update('users', [
                'failed_logins' => $fails,
                'locked_until'  => $fails >= 5 ? Clock::db($now->modify('+15 minutes')) : null,
            ], 'id = :id', ['id' => $u['id']]);
            return false;
        }
        if (password_needs_rehash($u['password_hash'], PASSWORD_DEFAULT)) {
            Db::update('users', ['password_hash' => password_hash($password, PASSWORD_DEFAULT)], 'id = :id', ['id' => $u['id']]);
        }
        Db::update('users', ['failed_logins' => 0, 'locked_until' => null, 'last_login_at' => Clock::nowDb()], 'id = :id', ['id' => $u['id']]);
        Session::regenerate();
        $_SESSION['admin_uid'] = (int)$u['id'];
        $_SESSION['admin_seen'] = time();
        self::$loaded = false;
        Audit::log('login', 'user', (string)$u['id']);
        return true;
    }

    public static function logout(): void
    {
        unset($_SESSION['admin_uid'], $_SESSION['admin_seen']);
        self::$user = null;
        Session::regenerate();
    }
}
