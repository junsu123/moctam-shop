<?php
declare(strict_types=1);

/**
 * Nhà cung cấp OAuth GIẢ LẬP cho kiểm thử (không dùng khi chạy thật).
 *   php -S 127.0.0.1:8099 tests/fake_oauth.php
 * "code" do bộ kiểm thử tạo = base64url(JSON hồ sơ người dùng + nonce + code_challenge).
 * Google: kiểm tra PKCE rồi trả id_token (chữ ký giả — website kiểm tra claims vì nhận trực tiếp qua TLS).
 * Facebook: access_token, /me kiểm tra appsecret_proof như Graph API thật.
 * Trang /authorize?…: mô phỏng màn hình đồng ý — chuyển thẳng về redirect_uri (dùng cho kiểm thử trình duyệt).
 */
const FB_SECRET = 'fb-test-secret';

function b64u(string $s): string { return rtrim(strtr(base64_encode($s), '+/', '-_'), '='); }
function b64ud(string $s): string { return (string)base64_decode(strtr($s, '-_', '+/') . str_repeat('=', (4 - strlen($s) % 4) % 4)); }
function out(array $d, int $st = 200): void { http_response_code($st); header('Content-Type: application/json'); echo json_encode($d); exit; }

$path = parse_url($_SERVER['REQUEST_URI'], PHP_URL_PATH);

if ($path === '/authorize') {
    // Mô phỏng người dùng bấm "Tiếp tục": hồ sơ lấy từ tham số login_hint của bộ kiểm thử (mặc định một người dùng mẫu)
    $profile = ['sub' => $_GET['uid'] ?? 'g-browser-1', 'email' => $_GET['email'] ?? 'khach.thu@gmail.com', 'email_verified' => true, 'name' => $_GET['name'] ?? 'Khách Thử',
        'nonce' => $_GET['nonce'] ?? null, 'challenge' => $_GET['code_challenge'] ?? null];
    header('Location: ' . $_GET['redirect_uri'] . '?' . http_build_query(['code' => b64u(json_encode($profile)), 'state' => $_GET['state']]), true, 302);
    exit;
}

if ($path === '/google/token' && $_SERVER['REQUEST_METHOD'] === 'POST') {
    $p = json_decode(b64ud($_POST['code'] ?? ''), true);
    if (!$p) out(['error' => 'invalid_grant'], 400);
    if (!empty($p['challenge']) && b64u(hash('sha256', (string)($_POST['code_verifier'] ?? ''), true)) !== $p['challenge']) {
        out(['error' => 'invalid_grant', 'error_description' => 'PKCE verifier mismatch'], 400);
    }
    $claims = ['iss' => $p['iss'] ?? 'https://accounts.google.com', 'aud' => $_POST['client_id'], 'sub' => $p['sub'], 'email' => $p['email'] ?? null,
        'email_verified' => $p['email_verified'] ?? false, 'name' => $p['name'] ?? '', 'nonce' => $p['nonce'] ?? '', 'iat' => time(), 'exp' => time() + ($p['ttl'] ?? 3600)];
    out(['access_token' => 'ya29.fake', 'token_type' => 'Bearer', 'expires_in' => 3599,
        'id_token' => b64u('{"alg":"RS256","kid":"fake"}') . '.' . b64u(json_encode($claims)) . '.' . b64u('fake-signature')]);
}

if ($path === '/fb/token') {
    if (($_GET['client_secret'] ?? '') !== FB_SECRET) out(['error' => ['message' => 'Invalid client_secret']], 400);
    out(['access_token' => 'EAA' . ($_GET['code'] ?? ''), 'token_type' => 'bearer', 'expires_in' => 5183944]);
}

if ($path === '/fb/me') {
    $tok = (string)($_GET['access_token'] ?? '');
    if (!hash_equals(hash_hmac('sha256', $tok, FB_SECRET), (string)($_GET['appsecret_proof'] ?? ''))) {
        out(['error' => ['message' => 'Invalid appsecret_proof provided in the API argument', 'code' => 100]], 400);
    }
    $p = json_decode(b64ud(substr($tok, 3)), true) ?: [];
    out(array_filter(['id' => $p['sub'] ?? null, 'name' => $p['name'] ?? null, 'email' => $p['email'] ?? null], fn($v) => $v !== null));
}

out(['error' => 'not_found'], 404);
