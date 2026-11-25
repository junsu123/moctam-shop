<?php
declare(strict_types=1);

namespace App\Core;

/** Nhật ký quản trị (FR-12). Loại bỏ khóa, mật khẩu và dữ liệu nhận dạng (NFR-02). */
final class Audit
{
    private const REDACT = ['password', 'password_hash', 'key_hash', 'api_key', 'app_key', 'token', 'access_token', 'ship_phone', 'phone', 'ship_address', 'ship_name', 'full_name'];

    public static function log(string $action, string $entityType, string $entityId, ?array $before = null, ?array $after = null, ?string $note = null, string $actorType = 'user'): void
    {
        $uid = $actorType === 'user' ? Auth::id() : null;
        Db::insert('audit_logs', [
            'actor_type'  => $uid === null && $actorType === 'user' ? 'system' : $actorType,
            'user_id'     => $uid,
            'action'      => $action,
            'entity_type' => $entityType,
            'entity_id'   => $entityId,
            'before_json' => $before === null ? null : json_enc(self::scrub($before)),
            'after_json'  => $after === null ? null : json_enc(self::scrub($after)),
            'note'        => $note === null ? null : mb_substr($note, 0, 500),
            'ip'          => PHP_SAPI === 'cli' ? null : client_ip(),
            'created_at'  => Clock::nowDb(),
        ]);
    }

    public static function scrub(array $data): array
    {
        foreach ($data as $k => $v) {
            if (is_string($k) && in_array(strtolower($k), self::REDACT, true)) {
                $data[$k] = '[đã ẩn]';
            } elseif (is_array($v)) {
                $data[$k] = self::scrub($v);
            }
        }
        return $data;
    }

    /** Ghi lỗi vận hành vào bảng error_logs (không chứa dữ liệu nhận dạng). */
    public static function error(string $channel, string $code, string $message): void
    {
        $message = preg_replace('/0\d{9}/', '[sđt]', $message) ?? $message;
        $message = preg_replace('/(Bearer\s+)\S+/i', '$1[khóa]', $message) ?? $message;
        try {
            Db::insert('error_logs', ['channel' => $channel, 'code' => $code, 'message' => mb_substr($message, 0, 1000), 'created_at' => Clock::nowDb()]);
        } catch (\Throwable) {
            error_log("[$channel] $code $message");
        }
    }
}
