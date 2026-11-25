<?php
declare(strict_types=1);

namespace App\Domain;

use App\Core\ApiError;
use App\Core\Audit;
use App\Core\Clock;
use App\Core\Db;
use App\Core\Session;
use App\Core\Text;
use App\Core\Ulid;

/**
 * Tài khoản khách (tùy chọn). Nhận diện theo danh tính nhà cung cấp (provider + uid).
 * Liên kết tự động sang tài khoản có sẵn CHỈ khi email đã được nhà cung cấp xác minh.
 * KHÔNG gộp đơn khách lẻ cũ theo SĐT (SĐT không được xác minh → tránh lộ đơn của người khác).
 */
final class CustomerAccountService
{
    public const PROVIDER_LABELS = ['google' => 'Google', 'facebook' => 'Facebook'];

    /**
     * Tài khoản đang đăng nhập. Phiên bị vô hiệu khi tài khoản đã bị xóa, đang khóa,
     * hoặc nhân viên đã "buộc đăng xuất" (session_version tăng sau khi phiên được tạo).
     */
    public static function current(): ?array
    {
        $id = (int)($_SESSION['acct_id'] ?? 0);
        if (!$id) return null;
        $a = Db::one('SELECT * FROM customer_accounts WHERE id = :id', ['id' => $id]);
        if (!$a || $a['locked_at'] !== null || (int)$a['session_version'] !== (int)($_SESSION['acct_ver'] ?? 0)) {
            unset($_SESSION['acct_id'], $_SESSION['acct_ver']);
            return null;
        }
        return $a;
    }

    public static function lockedError(): ApiError
    {
        return new ApiError('ACCOUNT_LOCKED', 'Tài khoản này đang tạm khóa đăng nhập. Bạn vẫn đặt hàng được mà không cần đăng nhập; vui lòng liên hệ hotline '
            . \App\Core\Settings::get('hotline') . ' để được hỗ trợ.', 403);
    }

    /** @param array{provider:string, uid:string, email:?string, email_verified:bool, name:string} $p */
    public static function loginWithProfile(array $p): int
    {
        return Db::tx(function () use ($p) {
            $now = Clock::nowDb();
            $ident = Db::one('SELECT * FROM account_identities WHERE provider = :p AND provider_uid = :u FOR UPDATE', ['p' => $p['provider'], 'u' => $p['uid']]);
            if ($ident) {
                $accountId = (int)$ident['account_id'];
                Db::update('account_identities', ['last_login_at' => $now, 'email' => $p['email'], 'email_verified' => $p['email_verified'] ? 1 : 0], 'id = :id', ['id' => $ident['id']]);
            } else {
                $accountId = 0;
                // đang đăng nhập → liên kết thêm nhà cung cấp. Dùng current() để phiên đã bị khóa/buộc đăng xuất không liên kết được
                $linkTo = (int)(self::current()['id'] ?? 0);
                if ($linkTo && Db::val('SELECT 1 FROM customer_accounts WHERE id = :id', ['id' => $linkTo])) {
                    $accountId = $linkTo;
                } elseif ($p['email'] && $p['email_verified']) {
                    $accountId = (int)Db::val('SELECT a.id FROM customer_accounts a JOIN account_identities i ON i.account_id = a.id
                                               WHERE a.email = :e AND i.email_verified = 1 ORDER BY a.id LIMIT 1', ['e' => $p['email']]);
                }
                if (!$accountId) {
                    $accountId = Db::insert('customer_accounts', [
                        'email' => $p['email_verified'] ? $p['email'] : null, 'display_name' => mb_substr($p['name'], 0, 120),
                        'created_at' => $now, 'updated_at' => $now,
                    ]);
                }
                Db::insert('account_identities', [
                    'account_id' => $accountId, 'provider' => $p['provider'], 'provider_uid' => $p['uid'], 'email' => $p['email'],
                    'email_verified' => $p['email_verified'] ? 1 : 0, 'created_at' => $now, 'last_login_at' => $now,
                ]);
            }
            $acc = Db::one('SELECT email, locked_at FROM customer_accounts WHERE id = :id FOR UPDATE', ['id' => $accountId]);
            // Tài khoản đang khóa: hoàn tác cả danh tính vừa liên kết (không cho "lách" khóa bằng nhà cung cấp khác cùng email)
            if ($acc['locked_at'] !== null) throw self::lockedError();
            $upd = ['last_login_at' => $now, 'updated_at' => $now];
            if (!$acc['email'] && $p['email'] && $p['email_verified']) $upd['email'] = $p['email'];
            Db::update('customer_accounts', $upd, 'id = :id', ['id' => $accountId]);
            return $accountId;
        });
    }

    public static function startSession(int $accountId): void
    {
        Session::regenerate(); // chống cố định phiên
        $_SESSION['acct_id'] = $accountId;
        $_SESSION['acct_ver'] = (int)Db::val('SELECT session_version FROM customer_accounts WHERE id = :id', ['id' => $accountId]);
    }

    public static function logout(): void
    {
        unset($_SESSION['acct_id'], $_SESSION['acct_ver']);
        Session::regenerate();
    }

    public static function updateProfile(int $accountId, array $in): void
    {
        $phone = trim((string)($in['ship_phone'] ?? ''));
        $data = [
            'display_name' => mb_substr(trim((string)($in['display_name'] ?? '')), 0, 120),
            'ship_name' => mb_substr(trim((string)($in['ship_name'] ?? '')), 0, 120) ?: null,
            'ship_phone' => $phone === '' ? null : Text::normalizePhone($phone),
            'ship_province' => mb_substr(trim((string)($in['ship_province'] ?? '')), 0, 80) ?: null,
            'ship_address' => mb_substr(trim((string)($in['ship_address'] ?? '')), 0, 400) ?: null,
            'updated_at' => Clock::nowDb(),
        ];
        $err = [];
        if (mb_strlen($data['display_name']) < 2) $err['display_name'] = 'Vui lòng nhập tên hiển thị';
        if ($phone !== '' && $data['ship_phone'] === null) $err['ship_phone'] = 'Số điện thoại di động Việt Nam chưa đúng';
        if ($data['ship_province'] && !ShippingService::zoneFor($data['ship_province'])) $err['ship_province'] = 'Khu vực này chưa được phục vụ';
        if ($err) throw ApiError::validation($err);
        Db::update('customer_accounts', $data, 'id = :id', ['id' => $accountId]);
    }

    /** Ghi nhớ thông tin giao hàng lần gần nhất (gọi trong giao dịch tạo đơn). */
    public static function rememberShipping(int $accountId, array $c): void
    {
        Db::update('customer_accounts', ['ship_name' => $c['name'], 'ship_phone' => $c['phone'], 'ship_province' => $c['province'], 'ship_address' => $c['address'], 'updated_at' => Clock::nowDb()],
            'id = :id', ['id' => $accountId]);
    }

    public static function orders(int $accountId, int $limit = 50): array
    {
        return Db::all('SELECT id, code, access_token, status, payment_method, payment_status, total, created_at,
                               (SELECT COUNT(*) FROM order_items i WHERE i.order_id = o.id) AS line_count
                          FROM orders o WHERE account_id = :a ORDER BY id DESC LIMIT :l', ['a' => $accountId, 'l' => $limit]);
    }

    /** Trạng thái nhận tin theo các SĐT đã dùng trong đơn của tài khoản. */
    public static function marketingConsent(int $accountId): ?bool
    {
        $rows = Db::all('SELECT DISTINCT c.marketing_consent FROM customers c JOIN orders o ON o.customer_id = c.id WHERE o.account_id = :a', ['a' => $accountId]);
        if (!$rows) return null;
        return (bool)max(array_column($rows, 'marketing_consent'));
    }

    public static function setMarketingConsent(int $accountId, bool $on): int
    {
        $n = Db::exec('UPDATE customers c JOIN orders o ON o.customer_id = c.id SET c.marketing_consent = :v, c.consent_updated_at = :t, c.updated_at = :t2
                        WHERE o.account_id = :a AND c.marketing_consent <> :v2',
            ['v' => $on ? 1 : 0, 'v2' => $on ? 1 : 0, 't' => Clock::nowDb(), 't2' => Clock::nowDb(), 'a' => $accountId]);
        Audit::log($on ? 'consent.granted' : 'consent.withdrawn', 'customer_account', (string)$accountId, null, ['customers' => $n], 'Khách tự thay đổi trên trang tài khoản', 'system');
        return $n;
    }

    /**
     * Xóa tài khoản: xóa danh tính đăng nhập + hồ sơ; đơn hàng giữ lại (nghĩa vụ kế toán) nhưng bỏ liên kết.
     * @return string mã xác nhận
     */
    public static function delete(int $accountId, string $source = 'self', ?string $note = null): string
    {
        $code = Ulid::code(16);
        Db::tx(function () use ($accountId, $source, $code) {
            $exists = (bool)Db::val('SELECT 1 FROM customer_accounts WHERE id = :id FOR UPDATE', ['id' => $accountId]);
            Db::exec('UPDATE orders SET account_id = NULL WHERE account_id = :a', ['a' => $accountId]);
            Db::exec('DELETE FROM customer_accounts WHERE id = :id', ['id' => $accountId]); // danh tính xóa theo ON DELETE CASCADE
            Db::insert('account_deletions', ['confirmation_code' => $code, 'source' => $source, 'status' => $exists ? 'completed' : 'not_found', 'requested_at' => Clock::nowDb()]);
        });
        Audit::log('account.deleted', 'customer_account', (string)$accountId, null, ['source' => $source, 'code' => $code], $note, $source === 'admin' ? 'user' : 'system');
        return $code;
    }

    /** Facebook: người dùng gỡ ứng dụng và yêu cầu xóa dữ liệu. */
    public static function deleteByFacebook(string $fbUserId): string
    {
        $ident = Db::one("SELECT account_id FROM account_identities WHERE provider = 'facebook' AND provider_uid = :u", ['u' => $fbUserId]);
        if (!$ident) {
            $code = Ulid::code(16);
            Db::insert('account_deletions', ['confirmation_code' => $code, 'source' => 'facebook', 'status' => 'not_found', 'requested_at' => Clock::nowDb()]);
            return $code;
        }
        $others = (int)Db::val("SELECT COUNT(*) FROM account_identities WHERE account_id = :a AND provider <> 'facebook'", ['a' => $ident['account_id']]);
        if ($others > 0) {
            // Tài khoản còn đăng nhập Google: chỉ xóa liên kết và dữ liệu nhận từ Facebook
            Db::exec("DELETE FROM account_identities WHERE provider = 'facebook' AND provider_uid = :u", ['u' => $fbUserId]);
            $code = Ulid::code(16);
            Db::insert('account_deletions', ['confirmation_code' => $code, 'source' => 'facebook', 'status' => 'completed', 'requested_at' => Clock::nowDb()]);
            Audit::log('account.facebook_unlinked', 'customer_account', (string)$ident['account_id'], null, ['code' => $code], null, 'system');
            return $code;
        }
        return self::delete((int)$ident['account_id'], 'facebook');
    }

    public static function identities(int $accountId): array
    {
        return Db::all('SELECT id, provider, email, email_verified, created_at, last_login_at FROM account_identities WHERE account_id = :a ORDER BY id', ['a' => $accountId]);
    }

    // ================================================================ Quản trị (quyền accounts.manage)

    /** Danh sách tài khoản cho Quản trị → Tài khoản khách. $f: q, status (locked|active), provider, page */
    public static function adminSearch(array $f, int $perPage = 50): array
    {
        $where = ['1=1'];
        $p = [];
        $q = trim((string)($f['q'] ?? ''));
        if ($q !== '') {
            $like = '%' . addcslashes(mb_strtolower($q), '%_\\') . '%';
            $cond = ['LOWER(a.email) LIKE :q1', 'LOWER(a.display_name) LIKE :q2', 'EXISTS (SELECT 1 FROM account_identities s WHERE s.account_id = a.id AND LOWER(s.email) LIKE :q3)'];
            $p += ['q1' => $like, 'q2' => $like, 'q3' => $like];
            $phone = Text::normalizePhone($q);
            if ($phone !== null) { $cond[] = 'a.ship_phone = :ph'; $p['ph'] = $phone; }
            if (ctype_digit($q)) { $cond[] = 'a.id = :id'; $p['id'] = (int)$q; }
            $where[] = '(' . implode(' OR ', $cond) . ')';
        }
        $st = (string)($f['status'] ?? '');
        if ($st === 'locked') $where[] = 'a.locked_at IS NOT NULL';
        if ($st === 'active') $where[] = 'a.locked_at IS NULL';
        $prov = (string)($f['provider'] ?? '');
        if (isset(self::PROVIDER_LABELS[$prov])) { $where[] = 'EXISTS (SELECT 1 FROM account_identities s2 WHERE s2.account_id = a.id AND s2.provider = :pv)'; $p['pv'] = $prov; }
        $w = implode(' AND ', $where);
        $page = max(1, (int)($f['page'] ?? 1));
        $total = (int)Db::val("SELECT COUNT(*) FROM customer_accounts a WHERE $w", $p);
        $rows = Db::all("SELECT a.id, a.email, a.display_name, a.ship_phone, a.last_login_at, a.locked_at, a.created_at,
                                (SELECT GROUP_CONCAT(DISTINCT i.provider ORDER BY i.provider) FROM account_identities i WHERE i.account_id = a.id) AS providers,
                                (SELECT COUNT(*) FROM orders o WHERE o.account_id = a.id) AS order_count
                           FROM customer_accounts a WHERE $w
                          ORDER BY a.last_login_at IS NULL, a.last_login_at DESC, a.id DESC LIMIT :l OFFSET :o", $p + ['l' => $perPage, 'o' => ($page - 1) * $perPage]);
        return ['rows' => $rows, 'total' => $total, 'page' => $page, 'pages' => (int)ceil($total / $perPage)];
    }

    public static function adminStats(): array
    {
        $r = Db::one("SELECT COUNT(*) AS total, SUM(locked_at IS NOT NULL) AS locked,
                             SUM(last_login_at >= UTC_TIMESTAMP() - INTERVAL 30 DAY) AS active30 FROM customer_accounts");
        return array_map('intval', $r ?: []);
    }

    public static function find(int $accountId): array
    {
        $a = Db::one('SELECT * FROM customer_accounts WHERE id = :id', ['id' => $accountId]);
        if (!$a) throw ApiError::notFound('Không tìm thấy tài khoản khách (có thể đã bị xóa).');
        return $a;
    }

    /** Khóa đăng nhập: chặn đăng nhập mới và đăng xuất ngay mọi phiên đang mở. Mua hàng không cần tài khoản vẫn bình thường. */
    public static function lock(int $accountId, string $reason): void
    {
        $reason = mb_substr(trim($reason), 0, 255);
        if (mb_strlen($reason) < 3) throw ApiError::validation(['reason' => 'Ghi lý do khóa (VD: khách báo mất tài khoản Google)']);
        Db::tx(function () use ($accountId, $reason) {
            $a = Db::one('SELECT locked_at FROM customer_accounts WHERE id = :id FOR UPDATE', ['id' => $accountId]);
            if (!$a) throw ApiError::notFound('Không tìm thấy tài khoản khách.');
            if ($a['locked_at'] !== null) throw new ApiError('ALREADY_LOCKED', 'Tài khoản đã đang khóa.', 409);
            Db::exec('UPDATE customer_accounts SET locked_at = :t, locked_reason = :r, session_version = session_version + 1, updated_at = :u WHERE id = :id',
                ['t' => Clock::nowDb(), 'r' => $reason, 'u' => Clock::nowDb(), 'id' => $accountId]);
        });
        Audit::log('account.locked', 'customer_account', (string)$accountId, ['locked' => false], ['locked' => true], $reason);
    }

    public static function unlock(int $accountId): void
    {
        $a = self::find($accountId);
        if ($a['locked_at'] === null) throw new ApiError('NOT_LOCKED', 'Tài khoản không bị khóa.', 409);
        Db::update('customer_accounts', ['locked_at' => null, 'locked_reason' => null, 'updated_at' => Clock::nowDb()], 'id = :id', ['id' => $accountId]);
        Audit::log('account.unlocked', 'customer_account', (string)$accountId, ['locked' => true, 'reason' => $a['locked_reason']], ['locked' => false]);
    }

    /** Buộc đăng xuất trên mọi thiết bị (khách vẫn đăng nhập lại được). */
    public static function revokeSessions(int $accountId): void
    {
        self::find($accountId);
        Db::exec('UPDATE customer_accounts SET session_version = session_version + 1, updated_at = :u WHERE id = :id', ['u' => Clock::nowDb(), 'id' => $accountId]);
        Audit::log('account.sessions_revoked', 'customer_account', (string)$accountId);
    }

    /**
     * Gỡ một cách đăng nhập (VD: khách mất tài khoản Facebook). Không gỡ cách đăng nhập cuối cùng —
     * khi đó dùng Xóa tài khoản. Phiên đang mở bị đăng xuất để phiên tạo bằng danh tính vừa gỡ không còn dùng được.
     */
    public static function unlinkIdentity(int $accountId, int $identityId): void
    {
        $ident = Db::tx(function () use ($accountId, $identityId) {
            $rows = Db::all('SELECT id, provider, email FROM account_identities WHERE account_id = :a FOR UPDATE', ['a' => $accountId]);
            $ident = array_values(array_filter($rows, fn($r) => (int)$r['id'] === $identityId))[0] ?? null;
            if (!$ident) throw ApiError::notFound('Cách đăng nhập này không thuộc tài khoản.');
            if (count($rows) <= 1) throw new ApiError('LAST_IDENTITY', 'Đây là cách đăng nhập duy nhất của tài khoản. Muốn ngừng hẳn, hãy khóa hoặc xóa tài khoản.', 409);
            Db::exec('DELETE FROM account_identities WHERE id = :id', ['id' => $identityId]);
            Db::exec('UPDATE customer_accounts SET session_version = session_version + 1, updated_at = :u WHERE id = :a', ['u' => Clock::nowDb(), 'a' => $accountId]);
            return $ident;
        });
        Audit::log('account.identity_unlinked', 'customer_account', (string)$accountId, ['provider' => $ident['provider'], 'identity_id' => (int)$ident['id']], null);
    }

    /** Lịch sử thao tác liên quan tới tài khoản (đăng nhập không ghi nhật ký — chỉ lưu thời điểm gần nhất). */
    public static function history(int $accountId, int $limit = 30): array
    {
        return Db::all("SELECT a.action, a.note, a.actor_type, a.created_at, u.full_name FROM audit_logs a LEFT JOIN users u ON u.id = a.user_id
                         WHERE a.entity_type = 'customer_account' AND a.entity_id = :id ORDER BY a.id DESC LIMIT :l", ['id' => (string)$accountId, 'l' => $limit]);
    }
}
