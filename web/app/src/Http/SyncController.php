<?php
declare(strict_types=1);

namespace App\Http;

use App\Core\ApiError;
use App\Core\Clock;
use App\Core\Db;
use App\Core\Http;
use App\Domain\DraftInbox;
use App\Domain\SyncService;

/**
 * API đồng bộ cho dịch vụ Python. Kiểm tra khóa + phạm vi quyền trên TỪNG yêu cầu.
 *   events:read   → /events, /snapshot
 *   catalog:read  → /catalog
 *   drafts:write  → /drafts
 */
final class SyncController
{
    public static function authenticate(string $scope): array
    {
        $hdr = $_SERVER['HTTP_AUTHORIZATION'] ?? ($_SERVER['REDIRECT_HTTP_AUTHORIZATION'] ?? '');
        if (!preg_match('/^Bearer\s+(\S{20,200})$/', (string)$hdr, $m)) {
            throw new ApiError('UNAUTHENTICATED', 'Thiếu khóa API.', 401);
        }
        $key = Db::one('SELECT * FROM api_keys WHERE key_hash = :h AND is_active = 1', ['h' => hash('sha256', $m[1])]);
        if (!$key) {
            throw new ApiError('UNAUTHENTICATED', 'Khóa API không hợp lệ.', 401);
        }
        if (!in_array($scope, array_map('trim', explode(',', $key['scopes'])), true)) {
            throw new ApiError('FORBIDDEN', "Khóa không có quyền $scope.", 403);
        }
        Db::exec('UPDATE api_keys SET last_used_at = :t WHERE id = :id', ['t' => Clock::nowDb(), 'id' => $key['id']]);
        return $key;
    }

    public function events(): never
    {
        self::authenticate('events:read');
        Http::json(SyncService::events(max(0, (int)($_GET['after'] ?? 0)), (int)($_GET['limit'] ?? 500)));
    }

    public function snapshot(): never
    {
        self::authenticate('events:read');
        Http::json(SyncService::snapshot(max(0, (int)($_GET['after_id'] ?? 0)), (int)($_GET['limit'] ?? 500)));
    }

    public function catalog(): never
    {
        self::authenticate('catalog:read');
        $data = SyncService::catalog();
        $data['unanswered_questions'] = Db::all("SELECT question, COUNT(*) AS n FROM chat_questions WHERE source = 'fallback' AND created_at >= :c GROUP BY question ORDER BY n DESC LIMIT 100", ['c' => Clock::db(Clock::now()->modify('-30 days'))]);
        Http::json($data);
    }

    public function drafts(): never
    {
        $key = self::authenticate('drafts:write');
        $body = Http::body();
        Http::json(DraftInbox::receive($key, (array)($body['items'] ?? [])));
    }
}
