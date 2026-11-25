<?php
declare(strict_types=1);

namespace App\Auth;

use App\Core\ApiError;
use App\Core\Clock;

/**
 * Đăng nhập Google (OpenID Connect, mã ủy quyền + PKCE + nonce) và Facebook (OAuth, appsecret_proof).
 * Không phụ thuộc thư viện ngoài. Cấu hình trong app/config.php → 'oauth'.
 * Đăng nhập là TÙY CHỌN: nhà cung cấp chưa cấu hình → không hiện nút; lỗi nhà cung cấp không ảnh hưởng bán hàng.
 */
final class OAuth
{
    public const LABELS = ['google' => 'Google', 'facebook' => 'Facebook'];
    private const FB_VERSION = 'v26.0';

    public static function cfg(string $provider): array
    {
        $c = (array)config("oauth.$provider", []);
        $fbv = (string)($c['graph_version'] ?? self::FB_VERSION);
        $defaults = [
            'google' => [
                'auth_url' => 'https://accounts.google.com/o/oauth2/v2/auth',
                'token_url' => 'https://oauth2.googleapis.com/token',
                'issuers' => ['https://accounts.google.com', 'accounts.google.com'],
            ],
            'facebook' => [
                'auth_url' => "https://www.facebook.com/$fbv/dialog/oauth",
                'token_url' => "https://graph.facebook.com/$fbv/oauth/access_token",
                'me_url' => "https://graph.facebook.com/$fbv/me",
            ],
        ][$provider] ?? [];
        return $c + $defaults;
    }

    public static function enabled(string $provider): bool
    {
        $c = self::cfg($provider);
        return isset(self::LABELS[$provider]) && trim((string)($c['client_id'] ?? '')) !== '' && trim((string)($c['client_secret'] ?? '')) !== '';
    }

    /** @return string[] */
    public static function enabledProviders(): array
    {
        return array_values(array_filter(array_keys(self::LABELS), [self::class, 'enabled']));
    }

    public static function redirectUri(string $provider): string
    {
        return rtrim((string)config('base_url'), '/') . "/auth/$provider/callback";
    }

    /** Bắt đầu: lưu state/nonce/PKCE trong phiên, trả URL chuyển hướng tới nhà cung cấp. */
    public static function start(string $provider, string $next): string
    {
        if (!self::enabled($provider)) {
            throw ApiError::notFound('Hình thức đăng nhập này chưa được bật.');
        }
        $c = self::cfg($provider);
        $state = self::b64(random_bytes(24));
        $verifier = self::b64(random_bytes(48));
        $nonce = self::b64(random_bytes(24));
        $_SESSION['oauth'][$state] = ['provider' => $provider, 'verifier' => $verifier, 'nonce' => $nonce, 'next' => self::safeNext($next), 'at' => time()];
        // chỉ giữ 5 lượt gần nhất (khách mở nhiều tab)
        $_SESSION['oauth'] = array_slice($_SESSION['oauth'], -5, null, true);
        $q = ['client_id' => $c['client_id'], 'redirect_uri' => self::redirectUri($provider), 'response_type' => 'code', 'state' => $state];
        if ($provider === 'google') {
            $q += ['scope' => 'openid email profile', 'nonce' => $nonce, 'prompt' => 'select_account',
                'code_challenge' => self::b64(hash('sha256', $verifier, true)), 'code_challenge_method' => 'S256'];
        } else {
            $q += ['scope' => 'public_profile,email'];
        }
        return $c['auth_url'] . '?' . http_build_query($q);
    }

    /**
     * Xử lý callback. @return array{provider:string, uid:string, email:?string, email_verified:bool, name:string, next:string}
     */
    public static function finish(string $provider, array $query): array
    {
        $state = (string)($query['state'] ?? '');
        $saved = $_SESSION['oauth'][$state] ?? null;
        unset($_SESSION['oauth'][$state]); // dùng một lần
        if (!$saved || $saved['provider'] !== $provider || time() - (int)$saved['at'] > 600) {
            throw new ApiError('OAUTH_STATE', 'Phiên đăng nhập đã hết hạn hoặc không hợp lệ. Vui lòng thử lại.', 400);
        }
        if (!empty($query['error'])) {
            throw new ApiError('OAUTH_DENIED', 'Bạn đã hủy đăng nhập.', 400, ['next' => $saved['next']]);
        }
        $code = (string)($query['code'] ?? '');
        if ($code === '') {
            throw new ApiError('OAUTH_CODE', 'Thiếu mã ủy quyền.', 400);
        }
        $profile = $provider === 'google' ? self::google($code, $saved) : self::facebook($code);
        return $profile + ['next' => $saved['next']];
    }

    private static function google(string $code, array $saved): array
    {
        $c = self::cfg('google');
        $tok = self::http('POST', $c['token_url'], [
            'code' => $code, 'client_id' => $c['client_id'], 'client_secret' => $c['client_secret'],
            'redirect_uri' => self::redirectUri('google'), 'grant_type' => 'authorization_code', 'code_verifier' => $saved['verifier'],
        ]);
        $jwt = (string)($tok['id_token'] ?? '');
        $parts = explode('.', $jwt);
        if (count($parts) !== 3) {
            throw new ApiError('OAUTH_TOKEN', 'Google không trả về thông tin đăng nhập hợp lệ.', 502);
        }
        // id_token nhận TRỰC TIẾP từ máy chủ token của Google qua TLS (OIDC Core 3.1.3.7):
        // kiểm tra người phát hành, ứng dụng nhận, hạn dùng và nonce.
        $claims = json_decode((string)self::b64d($parts[1]), true) ?: [];
        $aud = (array)($claims['aud'] ?? []);
        $now = Clock::now()->getTimestamp();
        if (!in_array($claims['iss'] ?? '', $c['issuers'], true)
            || !in_array($c['client_id'], $aud, true)
            || (int)($claims['exp'] ?? 0) < $now - 60
            || !hash_equals($saved['nonce'], (string)($claims['nonce'] ?? ''))
            || empty($claims['sub'])) {
            throw new ApiError('OAUTH_TOKEN', 'Không xác thực được thông tin đăng nhập Google.', 400);
        }
        $verified = ($claims['email_verified'] ?? false) === true || ($claims['email_verified'] ?? '') === 'true';
        return [
            'provider' => 'google', 'uid' => (string)$claims['sub'],
            'email' => isset($claims['email']) ? mb_strtolower((string)$claims['email']) : null, 'email_verified' => $verified,
            'name' => trim((string)($claims['name'] ?? '')) ?: (string)($claims['email'] ?? 'Khách hàng'),
        ];
    }

    private static function facebook(string $code): array
    {
        $c = self::cfg('facebook');
        $tok = self::http('GET', $c['token_url'] . '?' . http_build_query([
            'client_id' => $c['client_id'], 'client_secret' => $c['client_secret'], 'redirect_uri' => self::redirectUri('facebook'), 'code' => $code,
        ]));
        $access = (string)($tok['access_token'] ?? '');
        if ($access === '') {
            throw new ApiError('OAUTH_TOKEN', 'Facebook không trả về mã truy cập.', 502);
        }
        $me = self::http('GET', $c['me_url'] . '?' . http_build_query([
            'fields' => 'id,name,email', 'access_token' => $access, 'appsecret_proof' => hash_hmac('sha256', $access, (string)$c['client_secret']),
        ]));
        if (empty($me['id'])) {
            throw new ApiError('OAUTH_TOKEN', 'Không đọc được thông tin tài khoản Facebook.', 502);
        }
        return [
            'provider' => 'facebook', 'uid' => (string)$me['id'],
            // Facebook chỉ trả email chính đã xác nhận; người dùng có thể không cấp quyền email
            'email' => isset($me['email']) ? mb_strtolower((string)$me['email']) : null, 'email_verified' => isset($me['email']),
            'name' => trim((string)($me['name'] ?? '')) ?: 'Khách hàng',
        ];
    }

    /** Facebook gửi khi người dùng gỡ ứng dụng & yêu cầu xóa dữ liệu. @return array|null payload đã xác thực */
    public static function parseSignedRequest(string $signed): ?array
    {
        $secret = (string)(self::cfg('facebook')['client_secret'] ?? '');
        if ($secret === '' || !str_contains($signed, '.')) {
            return null;
        }
        [$sig, $payload] = explode('.', $signed, 2);
        $data = json_decode((string)self::b64d($payload), true);
        if (!is_array($data) || strtoupper((string)($data['algorithm'] ?? '')) !== 'HMAC-SHA256') {
            return null;
        }
        $expected = hash_hmac('sha256', $payload, $secret, true);
        return hash_equals($expected, (string)self::b64d($sig)) ? $data : null;
    }

    public static function safeNext(string $next): string
    {
        return (str_starts_with($next, '/') && !str_starts_with($next, '//') && !str_contains($next, '\\')) ? $next : '/tai-khoan';
    }

    /** Gọi HTTP tới nhà cung cấp (cURL, dự phòng stream). */
    private static function http(string $method, string $url, array $form = []): array
    {
        $timeout = 10;
        if (function_exists('curl_init')) {
            $ch = curl_init($url);
            curl_setopt_array($ch, [CURLOPT_RETURNTRANSFER => true, CURLOPT_TIMEOUT => $timeout, CURLOPT_CONNECTTIMEOUT => 5,
                CURLOPT_HTTPHEADER => ['Accept: application/json'], CURLOPT_SSL_VERIFYPEER => true]);
            if ($method === 'POST') {
                curl_setopt($ch, CURLOPT_POST, true);
                curl_setopt($ch, CURLOPT_POSTFIELDS, http_build_query($form));
            }
            $body = curl_exec($ch);
            $status = (int)curl_getinfo($ch, CURLINFO_RESPONSE_CODE);
            $err = curl_error($ch);
        } else {
            $ctx = stream_context_create(['http' => ['method' => $method, 'timeout' => $timeout, 'ignore_errors' => true,
                'header' => "Accept: application/json\r\nContent-Type: application/x-www-form-urlencoded\r\n", 'content' => $method === 'POST' ? http_build_query($form) : '']]);
            $body = @file_get_contents($url, false, $ctx);
            $status = (int)preg_replace('#^HTTP/\S+ (\d+).*$#', '$1', (string)(($http_response_header ?? [''])[0] ?? '0'));
            $err = $body === false ? 'không kết nối được' : '';
        }
        if ($body === false || $body === '' || $err !== '') {
            \App\Core\Audit::error('oauth', 'HTTP_FAILED', parse_url($url, PHP_URL_HOST) . ': ' . $err);
            throw new ApiError('OAUTH_UNAVAILABLE', 'Không kết nối được tới nhà cung cấp đăng nhập. Vui lòng thử lại hoặc tiếp tục mua không cần đăng nhập.', 502);
        }
        $data = json_decode((string)$body, true);
        if ($status >= 400 || !is_array($data)) {
            \App\Core\Audit::error('oauth', 'HTTP_' . $status, parse_url($url, PHP_URL_HOST) . ': ' . mb_substr((string)$body, 0, 200));
            throw new ApiError('OAUTH_TOKEN', 'Nhà cung cấp đăng nhập từ chối yêu cầu. Vui lòng thử lại.', 502);
        }
        return $data;
    }

    private static function b64(string $bin): string
    {
        return rtrim(strtr(base64_encode($bin), '+/', '-_'), '=');
    }

    private static function b64d(string $s): string|false
    {
        return base64_decode(strtr($s, '-_', '+/') . str_repeat('=', (4 - strlen($s) % 4) % 4), true);
    }
}
