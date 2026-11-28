<?php
declare(strict_types=1);

namespace App\Domain;

use App\Core\ApiError;
use App\Core\Audit;
use App\Core\Auth;
use App\Core\Clock;
use App\Core\Db;
use App\Core\Html;
use App\Core\Text;

/**
 * Blog, FAQ, trang chính sách: bản nháp → chờ duyệt → xuất bản, có lịch sử phiên bản (FR-09).
 * Địa chỉ (slug) cố định sau lần xuất bản đầu tiên.
 */
final class ContentService
{
    public const KIND_LABELS = ['blog' => 'Bài blog', 'faq' => 'Câu hỏi thường gặp', 'page' => 'Trang thông tin'];
    public const STATUS_LABELS = ['draft' => 'Bản nháp', 'pending_review' => 'Chờ duyệt', 'published' => 'Đã xuất bản', 'unpublished' => 'Đã gỡ'];

    /**
     * Tạo nội dung mới. $source='ai' → luôn ở trạng thái chờ duyệt, không tự xuất bản.
     */
    public static function create(string $kind, array $in, string $source = 'staff', bool $checkPerm = true): int
    {
        if ($checkPerm) Auth::require('content.edit');
        if (!isset(self::KIND_LABELS[$kind])) throw ApiError::validation(['kind' => 'Loại nội dung không hợp lệ']);
        $v = self::validateVersion($in);
        return Db::tx(function () use ($kind, $in, $source, $v) {
            $slug = self::uniqueSlug($kind, Text::slug(($in['slug'] ?? '') ?: $v['title']));
            $now = Clock::nowDb();
            $id = Db::insert('contents', [
                'kind' => $kind, 'slug' => $slug, 'status' => $source === 'ai' ? 'pending_review' : 'draft', 'source' => $source,
                'category_id' => !empty($in['category_id']) ? (int)$in['category_id'] : null,
                'product_id' => !empty($in['product_id']) ? (int)$in['product_id'] : null,
                'created_at' => $now, 'updated_at' => $now,
            ]);
            $vid = self::insertVersion($id, $v, $source);
            Db::update('contents', ['current_version_id' => $vid], 'id = :id', ['id' => $id]);
            Audit::log('content.create', 'content', (string)$id, null, ['kind' => $kind, 'title' => $v['title'], 'source' => $source], null, $source === 'ai' ? 'sync' : 'user');
            return $id;
        });
    }

    /** Lưu phiên bản mới (sửa bài). Bài đã xuất bản vẫn hiển thị bản cũ cho tới khi xuất bản lại. */
    public static function saveVersion(int $id, array $in, bool $submit = false): int
    {
        Auth::require('content.edit');
        $v = self::validateVersion($in);
        return Db::tx(function () use ($id, $in, $v, $submit) {
            $c = Db::one('SELECT * FROM contents WHERE id = :id FOR UPDATE', ['id' => $id]);
            if (!$c) throw ApiError::notFound();
            $vid = self::insertVersion($id, $v, 'staff');
            $upd = ['current_version_id' => $vid, 'updated_at' => Clock::nowDb(),
                'category_id' => !empty($in['category_id']) ? (int)$in['category_id'] : null,
                'product_id' => !empty($in['product_id']) ? (int)$in['product_id'] : null];
            if (!$c['published_version_id'] && !empty($in['slug'])) {
                $upd['slug'] = self::uniqueSlug($c['kind'], Text::slug($in['slug']), $id); // chỉ đổi slug khi chưa từng xuất bản
            }
            if ($submit && in_array($c['status'], ['draft', 'unpublished'], true)) $upd['status'] = 'pending_review';
            Db::update('contents', $upd, 'id = :id', ['id' => $id]);
            Audit::log('content.version', 'content', (string)$id, null, ['version_id' => $vid, 'title' => $v['title']]);
            return $vid;
        });
    }

    public static function submit(int $id): void
    {
        Auth::require('content.edit');
        Db::exec("UPDATE contents SET status = 'pending_review', updated_at = :t WHERE id = :id AND status IN ('draft','unpublished')", ['t' => Clock::nowDb(), 'id' => $id]);
        Audit::log('content.submit', 'content', (string)$id);
    }

    public static function publish(int $id, ?int $versionId = null, ?string $note = null): void
    {
        Auth::require('content.publish');
        Db::tx(function () use ($id, $versionId, $note) {
            $c = Db::one('SELECT * FROM contents WHERE id = :id FOR UPDATE', ['id' => $id]);
            if (!$c) throw ApiError::notFound();
            $vid = $versionId ?: (int)$c['current_version_id'];
            $v = Db::one('SELECT * FROM content_versions WHERE id = :v AND content_id = :c', ['v' => $vid, 'c' => $id]);
            if (!$v) throw ApiError::notFound('Không tìm thấy phiên bản.');
            $now = Clock::nowDb();
            Db::update('contents', [
                'status' => 'published', 'published_version_id' => $vid, 'published_by' => 'staff',
                'pub_title' => $v['title'], 'pub_meta_description' => $v['meta_description'] ?: Text::excerpt($v['body'], 155),
                'pub_body' => $v['body'], 'pub_search_text' => Text::fold($v['title'] . ' ' . $v['keywords'] . ' ' . Text::excerpt($v['body'], 600)),
                'published_at' => $c['published_at'] ?? $now, 'updated_at' => $now,
            ], 'id = :id', ['id' => $id]);
            Db::update('content_versions', ['reviewed_by' => Auth::id(), 'reviewed_at' => $now, 'review_note' => $note ? mb_substr($note, 0, 500) : null], 'id = :id', ['id' => $vid]);
            Audit::log('content.publish', 'content', (string)$id, ['status' => $c['status'], 'version' => $c['published_version_id']], ['status' => 'published', 'version' => $vid], $note);
        });
    }

    /**
     * Xuất bản bài do AI tạo, không qua tài khoản nhân viên (chỉ gọi từ AiPublisher sau khi đã kiểm khóa `content:publish`,
     * khung giờ và hạn mức). Chỉ áp cho nội dung source='ai' đang chờ duyệt.
     */
    public static function publishAsAi(int $id, string $note): void
    {
        $c = Db::one('SELECT * FROM contents WHERE id = :id FOR UPDATE', ['id' => $id]);
        if (!$c || $c['source'] !== 'ai' || $c['status'] !== 'pending_review') {
            throw new ApiError('FORBIDDEN', 'Chỉ xuất bản được nội dung AI vừa tạo.', 403);
        }
        $v = Db::one('SELECT * FROM content_versions WHERE id = :v', ['v' => (int)$c['current_version_id']]);
        $now = Clock::nowDb();
        Db::update('contents', [
            'status' => 'published', 'published_version_id' => (int)$v['id'], 'published_by' => 'ai',
            'pub_title' => $v['title'], 'pub_meta_description' => $v['meta_description'] ?: Text::excerpt($v['body'], 155),
            'pub_body' => $v['body'], 'pub_search_text' => Text::fold($v['title'] . ' ' . $v['keywords'] . ' ' . Text::excerpt($v['body'], 600)),
            'published_at' => $now, 'updated_at' => $now,
        ], 'id = :id', ['id' => $id]);
        Db::update('content_versions', ['reviewed_at' => $now, 'review_note' => mb_substr($note, 0, 500)], 'id = :id', ['id' => (int)$v['id']]);
        Audit::log('content.ai_publish', 'content', (string)$id, ['status' => $c['status']], ['status' => 'published', 'version' => (int)$v['id']], $note, 'sync');
    }

    public static function unpublish(int $id, string $reason): void
    {
        Auth::require('content.publish');
        Db::tx(function () use ($id, $reason) {
            $c = Db::one('SELECT * FROM contents WHERE id = :id FOR UPDATE', ['id' => $id]);
            if (!$c) throw ApiError::notFound();
            Db::update('contents', ['status' => 'unpublished', 'updated_at' => Clock::nowDb()], 'id = :id', ['id' => $id]);
            Audit::log('content.unpublish', 'content', (string)$id, ['status' => $c['status']], ['status' => 'unpublished'], $reason);
        });
    }

    public static function reject(int $id, string $note): void
    {
        Auth::require('content.publish');
        Db::tx(function () use ($id, $note) {
            $c = Db::one('SELECT * FROM contents WHERE id = :id FOR UPDATE', ['id' => $id]);
            if (!$c) throw ApiError::notFound();
            Db::update('contents', ['status' => $c['published_version_id'] ? 'published' : 'draft', 'updated_at' => Clock::nowDb()], 'id = :id', ['id' => $id]);
            Db::update('content_versions', ['review_note' => 'Từ chối: ' . mb_substr($note, 0, 480), 'reviewed_by' => Auth::id(), 'reviewed_at' => Clock::nowDb()], 'id = :id', ['id' => $c['current_version_id']]);
            Audit::log('content.reject', 'content', (string)$id, null, null, $note);
        });
    }

    private static function validateVersion(array $in): array
    {
        $title = trim((string)($in['title'] ?? ''));
        $body = (string)($in['body'] ?? '');
        if (!empty($in['body_is_text'])) $body = Html::fromText($body);
        $body = Html::sanitize($body);
        $err = [];
        if (mb_strlen($title) < 3) $err['title'] = 'Tiêu đề tối thiểu 3 ký tự';
        if (trim(strip_tags($body)) === '') $err['body'] = 'Nội dung không được trống';
        if ($err) throw ApiError::validation($err);
        return [
            'title' => mb_substr($title, 0, 250),
            'meta_description' => mb_substr(trim((string)($in['meta_description'] ?? '')), 0, 320) ?: null,
            'body' => $body,
            'keywords' => mb_substr(trim((string)($in['keywords'] ?? '')), 0, 500) ?: null,
            'source_refs' => isset($in['source_refs']) ? json_enc($in['source_refs']) : null,
        ];
    }

    private static function insertVersion(int $contentId, array $v, string $source): int
    {
        $no = (int)Db::val('SELECT COALESCE(MAX(version_no),0)+1 FROM content_versions WHERE content_id = :c', ['c' => $contentId]);
        return Db::insert('content_versions', $v + [
            'content_id' => $contentId, 'version_no' => $no, 'created_by' => $source === 'ai' ? null : Auth::id(),
            'created_source' => $source, 'created_at' => Clock::nowDb(),
        ]);
    }

    private static function uniqueSlug(string $kind, string $slug, ?int $exceptId = null): string
    {
        // Blog và trang có địa chỉ riêng /{slug}.html → duy nhất toàn site. FAQ chỉ cần duy nhất trong loại.
        if ($kind === 'blog' || $kind === 'page') return Urls::unique($slug, $kind, $exceptId);
        $base = $slug;
        $i = 2;
        while (Db::val('SELECT 1 FROM contents WHERE kind = :k AND slug = :s AND id <> :id', ['k' => $kind, 's' => $slug, 'id' => $exceptId ?? 0])) {
            $slug = $base . '-' . $i++;
        }
        return $slug;
    }

    // -------------------------------------------------------------- công khai

    public static function published(string $kind, int $page = 1, int $perPage = 9): array
    {
        $total = (int)Db::val("SELECT COUNT(*) FROM contents WHERE kind = :k AND status = 'published'", ['k' => $kind]);
        $pages = max(1, (int)ceil($total / $perPage));
        $page = max(1, min($page, $pages));
        $items = Db::all("SELECT id, slug, pub_title, pub_meta_description, pub_body, cover_image, published_at, category_id, product_id FROM contents WHERE kind = :k AND status = 'published' ORDER BY published_at DESC, id DESC LIMIT :l OFFSET :o",
            ['k' => $kind, 'l' => $perPage, 'o' => ($page - 1) * $perPage]);
        return ['items' => $items, 'page' => $page, 'pages' => $pages, 'total' => $total];
    }

    public static function bySlug(string $kind, string $slug): ?array
    {
        return Db::one("SELECT * FROM contents WHERE kind = :k AND slug = :s AND status = 'published'", ['k' => $kind, 's' => $slug]);
    }
}
