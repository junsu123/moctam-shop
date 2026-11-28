<?php
declare(strict_types=1);

namespace App\Domain;

use App\Core\ApiError;
use App\Core\Audit;
use App\Core\Clock;
use App\Core\Db;
use App\Core\Settings;

/**
 * AI tự xuất bản FAQ/blog (khóa `content:publish`) — lớp chặn cuối cùng ở phía website:
 *   - chỉ tạo và xuất bản nội dung MỚI có source='ai' (không đụng được bài của nhân viên);
 *   - thông tin sản phẩm phải còn đúng phiên bản (`info_version`), HTML qua bộ lọc danh sách trắng như mọi bài;
 *   - chỉ trong khung giờ cho phép và trong hạn mức NGÀY đếm ở website (máy Python có lỗi cũng không vượt được);
 *   - `ai_publish_enabled = 0` hoặc thu hồi khóa là dừng ngay; mọi lần xuất bản/gỡ đều ghi audit.
 * Gửi lại cùng client_ref không tạo bài thứ hai.
 */
final class AiPublisher
{
    public const KINDS = ['faq', 'blog'];

    public static function publish(array $apiKey, array $in): array
    {
        $ref = substr(preg_replace('/[^A-Za-z0-9_.:\-]/', '', (string)($in['client_ref'] ?? '')) ?? '', 0, 80);
        $kind = (string)($in['kind'] ?? '');
        if ($ref === '') throw ApiError::validation(['client_ref' => 'Bắt buộc']);
        if (!in_array($kind, self::KINDS, true)) throw ApiError::validation(['kind' => 'Chỉ xuất bản được faq hoặc blog']);
        $old = Db::one('SELECT * FROM ai_publications WHERE api_key_id = :k AND client_ref = :r', ['k' => $apiKey['id'], 'r' => $ref]);
        if ($old) return self::result((int)$old['content_id'], true);
        if (Settings::get('ai_publish_enabled', '1') !== '1') {
            throw new ApiError('AI_PUBLISH_DISABLED', 'Website đang tắt chức năng AI tự xuất bản.', 423);
        }
        self::checkHours();
        $d = (array)($in['data'] ?? []);
        return Db::tx(function () use ($apiKey, $ref, $kind, $d) {
            // Khóa đếm hạn mức: hai yêu cầu song song không cùng lọt qua
            Db::one("SELECT `value` FROM settings WHERE `key` = 'ai_publish_limit_$kind' FOR UPDATE");
            $limit = Settings::int("ai_publish_limit_$kind", $kind === 'faq' ? 3 : 1);
            [$from, $to] = self::today();
            $used = (int)Db::val('SELECT COUNT(*) FROM ai_publications WHERE kind = :k AND published_at >= :f AND published_at < :t',
                ['k' => $kind, 'f' => $from, 't' => $to]);
            if ($used >= $limit) {
                throw new ApiError('AI_PUBLISH_QUOTA', "Đã hết hạn mức AI xuất bản $kind hôm nay ($used/$limit).", 429, ['used' => $used, 'limit' => $limit]);
            }
            foreach ((array)($d['source_refs'] ?? []) as $r) {
                if (isset($r['product_id'], $r['info_version'])) {
                    $cur = (int)Db::val('SELECT info_version FROM products WHERE id = :id', ['id' => (int)$r['product_id']]);
                    if ($cur && $cur !== (int)$r['info_version']) {
                        throw new ApiError('SOURCE_OUTDATED', "Thông tin sản phẩm #{$r['product_id']} đã đổi (v$cur), bài dựa trên v{$r['info_version']}.", 409);
                    }
                }
            }
            $id = ContentService::create($kind, [
                'title' => $d['title'] ?? '', 'body' => $d['body'] ?? '', 'body_is_text' => !empty($d['body_is_text']),
                'meta_description' => $d['meta_description'] ?? null, 'keywords' => $d['keywords'] ?? null,
                'category_id' => $d['category_id'] ?? null, 'product_id' => $d['product_id'] ?? null,
                'source_refs' => (array)($d['source_refs'] ?? []) + ['generated_by' => mb_substr((string)($d['generated_by'] ?? 'python'), 0, 60)],
            ], 'ai', false);
            ContentService::publishAsAi($id, 'AI tự xuất bản (khóa ' . $apiKey['key_prefix'] . ', ' . $ref . ')');
            $now = Clock::nowDb();
            Db::insert('ai_publications', ['api_key_id' => $apiKey['id'], 'client_ref' => $ref, 'content_id' => $id, 'kind' => $kind, 'published_at' => $now]);
            // Kênh phản hồi chung (/api/sync/feedback): bài AI đã xuất bản báo 'approved', bị gỡ báo 'retracted'
            Db::run('INSERT IGNORE INTO sync_inbox (api_key_id, client_ref, kind, status, result, created_at) VALUES (:k,:r,:kind,\'accepted\',:res,:t)',
                ['k' => $apiKey['id'], 'r' => $ref, 'kind' => $kind, 'res' => "content:$id", 't' => $now]);
            return self::result($id, false) + ['quota' => ['used' => $used + 1, 'limit' => $limit]];
        });
    }

    public static function unpublish(array $apiKey, array $in): array
    {
        $reason = trim(mb_substr((string)($in['reason'] ?? ''), 0, 500));
        if ($reason === '') throw ApiError::validation(['reason' => 'Ghi lý do gỡ bài']);
        $row = null;
        if (!empty($in['content_id'])) {
            $row = Db::one('SELECT * FROM ai_publications WHERE content_id = :c ORDER BY id DESC LIMIT 1', ['c' => (int)$in['content_id']]);
        } elseif (!empty($in['client_ref'])) {
            $row = Db::one('SELECT * FROM ai_publications WHERE api_key_id = :k AND client_ref = :r', ['k' => $apiKey['id'], 'r' => (string)$in['client_ref']]);
        }
        if (!$row) {
            if (!empty($in['content_id']) && Db::val('SELECT id FROM contents WHERE id = :id', ['id' => (int)$in['content_id']])) {
                throw new ApiError('FORBIDDEN', 'Khóa AI chỉ gỡ được bài do AI xuất bản.', 403);
            }
            throw ApiError::notFound('Không có bài AI này.');
        }
        $id = (int)$row['content_id'];
        Db::tx(function () use ($id, $row, $reason) {
            $c = Db::one('SELECT status FROM contents WHERE id = :id FOR UPDATE', ['id' => $id]);
            if ($c && $c['status'] === 'published') {
                Db::update('contents', ['status' => 'unpublished', 'updated_at' => Clock::nowDb()], 'id = :id', ['id' => $id]);
                Audit::log('content.ai_unpublish', 'content', (string)$id, ['status' => 'published'], ['status' => 'unpublished'], $reason, 'sync');
            }
            if (!$row['unpublished_at']) {
                Db::update('ai_publications', ['unpublished_at' => Clock::nowDb(), 'unpublish_reason' => $reason], 'id = :id', ['id' => $row['id']]);
            }
        });
        return self::result($id, false);
    }

    /** Khung giờ cho phép theo giờ Việt Nam, vd "07:00-21:30". */
    private static function checkHours(): void
    {
        $win = Settings::get('ai_publish_hours', '07:00-21:30');
        if (!preg_match('/^(\d{2}):(\d{2})-(\d{2}):(\d{2})$/', $win, $m)) return;
        $local = Clock::now()->setTimezone(new \DateTimeZone(Clock::LOCAL_TZ));
        $mins = (int)$local->format('H') * 60 + (int)$local->format('i');
        if ($mins < (int)$m[1] * 60 + (int)$m[2] || $mins > (int)$m[3] * 60 + (int)$m[4]) {
            throw new ApiError('AI_PUBLISH_HOURS', "Chỉ xuất bản trong khung $win (giờ Việt Nam).", 409);
        }
    }

    /** Đầu và cuối ngày hôm nay theo giờ Việt Nam, đổi ra UTC để so với cột lưu UTC. */
    private static function today(): array
    {
        $tz = new \DateTimeZone(Clock::LOCAL_TZ);
        $start = Clock::now()->setTimezone($tz)->setTime(0, 0);
        return [Clock::db($start), Clock::db($start->modify('+1 day'))];
    }

    private static function result(int $id, bool $duplicate): array
    {
        $c = Db::one('SELECT id, kind, slug, status, published_at FROM contents WHERE id = :id', ['id' => $id]);
        $out = ['content_id' => $id, 'kind' => $c['kind'] ?? null, 'status' => $c['status'] ?? 'gone', 'published_at' => $c['published_at'] ?? null,
                'url' => $c ? Seo::abs($c['kind'] === 'blog' ? Urls::to($c['slug']) : Urls::fixed('faq')) : null];
        if ($duplicate) $out['duplicate'] = true;
        return $out;
    }
}
