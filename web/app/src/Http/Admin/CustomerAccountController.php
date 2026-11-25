<?php
declare(strict_types=1);

namespace App\Http\Admin;

use App\Core\ApiError;
use App\Domain\CustomerAccountService as Accounts;

/**
 * Quản trị → Tài khoản khách: tài khoản đăng nhập tùy chọn bằng Google / Facebook.
 * Mọi thao tác cần quyền accounts.manage (máy chủ kiểm tra trên từng yêu cầu) và được ghi nhật ký.
 */
final class CustomerAccountController extends Base
{
    public function index(): string
    {
        $this->need('accounts.manage');
        $f = array_intersect_key($_GET, array_flip(['q', 'status', 'provider', 'page']));
        $f = array_map(fn($v) => is_string($v) ? trim($v) : '', $f);
        return $this->view('customer_accounts', ['title' => 'Tài khoản khách', 'f' => $f, 'stats' => Accounts::adminStats()] + Accounts::adminSearch($f));
    }

    public function show(string $id): string
    {
        $this->need('accounts.manage');
        $a = Accounts::find((int)$id);
        return $this->view('customer_account_show', [
            'title' => 'Tài khoản khách #' . (int)$a['id'],
            'a' => $a,
            'identities' => Accounts::identities((int)$a['id']),
            'orders' => Accounts::orders((int)$a['id'], 20),
            'orderCount' => (int)\App\Core\Db::val('SELECT COUNT(*) FROM orders WHERE account_id = :a', ['a' => (int)$a['id']]),
            'consent' => Accounts::marketingConsent((int)$a['id']),
            'history' => Accounts::history((int)$a['id']),
        ]);
    }

    public function lock(string $id): void
    {
        $this->need('accounts.manage');
        Accounts::lock((int)$id, $this->str('reason'));
        $this->back('Đã khóa đăng nhập và đăng xuất khách khỏi mọi thiết bị.');
    }

    public function unlock(string $id): void
    {
        $this->need('accounts.manage');
        Accounts::unlock((int)$id);
        $this->back('Đã mở khóa. Khách đăng nhập lại được.');
    }

    public function logout(string $id): void
    {
        $this->need('accounts.manage');
        Accounts::revokeSessions((int)$id);
        $this->back('Đã đăng xuất khách khỏi mọi thiết bị.');
    }

    public function unlink(string $id): void
    {
        $this->need('accounts.manage');
        Accounts::unlinkIdentity((int)$id, $this->int('identity_id'));
        $this->back('Đã gỡ cách đăng nhập và đăng xuất các phiên đang mở.');
    }

    public function delete(string $id): void
    {
        $this->need('accounts.manage');
        $reason = mb_substr($this->str('delete_reason'), 0, 255);
        $err = [];
        if (mb_strlen($reason) < 3) $err['delete_reason'] = 'Ghi kênh và thời điểm khách yêu cầu (VD: khách gọi hotline 26/11)';
        if ($this->str('confirm') !== '1') $err['confirm'] = 'Đánh dấu ô xác nhận';
        if ($err) throw ApiError::validation($err);
        Accounts::find((int)$id);
        $code = Accounts::delete((int)$id, 'admin', $reason);
        $this->back("Đã xóa tài khoản. Mã xác nhận gửi cho khách: $code (tra cứu tại /tai-khoan/trang-thai-xoa).", '/admin/customer-accounts');
    }
}
