<?php
declare(strict_types=1);

namespace App\Http\Admin;

use App\Core\Auth;
use App\Core\Http;
use App\Core\RateLimiter;
use App\Core\Session;
use App\Core\View;

final class AuthController extends Base
{
    public function loginForm(): string
    {
        if (Auth::user()) Http::redirect('/admin');
        return View::render('admin/login', ['flash' => Session::takeFlash(), 'email' => $_SESSION['_old']['email'] ?? '']);
    }

    public function login(): void
    {
        RateLimiter::hit('admin_login', 10, 600);
        $email = $this->str('email');
        if (Auth::attempt($email, (string)($_POST['password'] ?? ''))) {
            $to = $_SESSION['after_login'] ?? '/admin';
            unset($_SESSION['after_login']);
            Http::redirect(str_starts_with($to, '/admin') ? $to : '/admin');
        }
        $_SESSION['_old'] = ['email' => $email];
        Session::flash('error', 'Email hoặc mật khẩu không đúng, hoặc tài khoản đang tạm khóa 15 phút do nhập sai nhiều lần.');
        Http::redirect('/admin/login');
    }

    public function logout(): void
    {
        Auth::logout();
        Http::redirect('/admin/login');
    }
}
