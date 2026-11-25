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
    public static function current(): ?array
    {
        $id = $_SESSION['acct_id'] ?? null;
        if (!$id) return null;
        static $cache = [];
        return $cache[$id] ??= (Db::one('SELECT * FROM customer_accounts WHERE id = :id', ['id' => (int)$id]) ?: null);
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
                $linkTo = (int)($_SESSION['acct_id'] ?? 0); // đang đăng nhập → liên kết thêm nhà cung cấp
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
            $acc = Db::one('SELECT email FROM customer_accounts WHERE id = :id', ['id' => $accountId]);
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
    }

    public static function logout(): void
    {
        unset($_SESSION['acct_id']);
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
    public static function delete(int $accountId, string $source = 'self'): string
    {
        $code = Ulid::code(16);
        Db::tx(function () use ($accountId, $source, $code) {
            $exists = (bool)Db::val('SELECT 1 FROM customer_accounts WHERE id = :id FOR UPDATE', ['id' => $accountId]);
            Db::exec('UPDATE orders SET account_id = NULL WHERE account_id = :a', ['a' => $accountId]);
            Db::exec('DELETE FROM customer_accounts WHERE id = :id', ['id' => $accountId]); // danh tính xóa theo ON DELETE CASCADE
            Db::insert('account_deletions', ['confirmation_code' => $code, 'source' => $source, 'status' => $exists ? 'completed' : 'not_found', 'requested_at' => Clock::nowDb()]);
        });
        Audit::log('account.deleted', 'customer_account', (string)$accountId, null, ['source' => $source, 'code' => $code], null, 'system');
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
        return Db::all('SELECT provider, email, created_at, last_login_at FROM account_identities WHERE account_id = :a ORDER BY id', ['a' => $accountId]);
    }
}
