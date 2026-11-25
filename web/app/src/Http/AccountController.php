<?php
declare(strict_types=1);

namespace App\Http;

use App\Auth\OAuth;
use App\Core\ApiError;
use App\Core\Csrf;
use App\Core\Db;
use App\Core\Http;
use App\Core\RateLimiter;
use App\Core\Session;
use App\Core\View;
use App\Domain\CatalogService;
use App\Domain\CustomerAccountService as Accounts;
use App\Domain\OrderService;
use App\Domain\ShippingService;

/** Đăng nhập tùy chọn bằng Google / Facebook và trang tài khoản của khách. */
final class AccountController
{
    private function render(string $view, array $data): string
    {
        $data['categories'] ??= CatalogService::categories();
        $data['robots'] = 'noindex';
        $data['notices'] = Session::takeFlash();
        return View::render('store/' . $view, $data, 'store/layout');
    }

    public function loginForm(): string
    {
        if (Accounts::current()) Http::redirect(OAuth::safeNext((string)($_GET['next'] ?? '/tai-khoan')));
        return $this->render('login', ['title' => 'Đăng nhập', 'providers' => OAuth::enabledProviders(), 'next' => OAuth::safeNext((string)($_GET['next'] ?? '/tai-khoan'))]);
    }

    public function start(string $provider): void
    {
        RateLimiter::hit('oauth', 30, 600);
        Http::redirect(OAuth::start($provider, (string)($_GET['next'] ?? '/tai-khoan')), 302);
    }

    public function callback(string $provider): void
    {
        RateLimiter::hit('oauth', 30, 600);
        try {
            $p = OAuth::finish($provider, $_GET);
        } catch (ApiError $e) {
            Session::flash('error', $e->getMessage());
            Http::redirect('/tai-khoan/dang-nhap' . (isset($e->data['next']) ? '?next=' . rawurlencode($e->data['next']) : ''));
        }
        $id = Accounts::loginWithProfile($p);
        Accounts::startSession($id);
        Session::flash('ok', 'Đã đăng nhập bằng ' . OAuth::LABELS[$provider] . '.');
        Http::redirect($p['next']);
    }

    public function logout(): void
    {
        Csrf::verifyRequest();
        Accounts::logout();
        Session::flash('ok', 'Đã đăng xuất.');
        Http::redirect('/');
    }

    private function requireAccount(): array
    {
        $a = Accounts::current();
        if (!$a) Http::redirect('/tai-khoan/dang-nhap?next=' . rawurlencode($_SERVER['REQUEST_URI'] ?? '/tai-khoan'));
        return $a;
    }

    public function show(): string
    {
        $a = $this->requireAccount();
        return $this->render('account', [
            'title' => 'Tài khoản của tôi', 'a' => $a,
            'orders' => Accounts::orders((int)$a['id']),
            'identities' => Accounts::identities((int)$a['id']),
            'consent' => Accounts::marketingConsent((int)$a['id']),
            'providers' => OAuth::enabledProviders(),
            'provinces' => ShippingService::servedProvinces(),
            'errors' => $_SESSION['_acct_errors'] ?? [],
        ]);
    }

    public function saveProfile(): void
    {
        Csrf::verifyRequest();
        $a = $this->requireAccount();
        unset($_SESSION['_acct_errors']);
        try {
            Accounts::updateProfile((int)$a['id'], $_POST);
            Session::flash('ok', 'Đã lưu thông tin.');
        } catch (ApiError $e) {
            $_SESSION['_acct_errors'] = $e->data['fields'] ?? [];
            Session::flash('error', $e->getMessage());
        }
        Http::redirect('/tai-khoan#thong-tin');
    }

    public function consent(): void
    {
        Csrf::verifyRequest();
        $a = $this->requireAccount();
        $on = ($_POST['consent'] ?? '') === '1';
        Accounts::setMarketingConsent((int)$a['id'], $on);
        Session::flash('ok', $on ? 'Bạn sẽ nhận tin nhắc mua lại và ưu đãi.' : 'Đã ngừng gửi tin nhắc mua lại và ưu đãi.');
        Http::redirect('/tai-khoan#nhan-tin');
    }

    public function delete(): void
    {
        Csrf::verifyRequest();
        $a = $this->requireAccount();
        if (($_POST['confirm'] ?? '') !== '1') {
            Session::flash('error', 'Vui lòng đánh dấu ô xác nhận trước khi xóa tài khoản.');
            Http::redirect('/tai-khoan#xoa');
        }
        $code = Accounts::delete((int)$a['id']);
        Accounts::logout();
        Http::redirect('/tai-khoan/trang-thai-xoa?ma=' . $code);
    }

    /** Callback xóa dữ liệu của Facebook (POST signed_request, không có cookie/CSRF). */
    public function facebookDeletion(): void
    {
        $data = OAuth::parseSignedRequest((string)($_POST['signed_request'] ?? ''));
        if (!$data || empty($data['user_id'])) {
            Http::json(['error' => ['code' => 'INVALID_SIGNED_REQUEST', 'message' => 'Yêu cầu không hợp lệ.']], 400);
        }
        $code = Accounts::deleteByFacebook((string)$data['user_id']);
        Http::json(['url' => rtrim((string)config('base_url'), '/') . '/tai-khoan/trang-thai-xoa?ma=' . $code, 'confirmation_code' => $code]);
    }

    public function deletionStatus(): string
    {
        $code = preg_replace('/[^A-Z0-9]/', '', strtoupper((string)($_GET['ma'] ?? ''))) ?? '';
        $row = $code !== '' ? Db::one('SELECT * FROM account_deletions WHERE confirmation_code = :c', ['c' => $code]) : null;
        return $this->render('deletion_status', ['title' => 'Trạng thái xóa dữ liệu', 'code' => $code, 'row' => $row]);
    }
}
