<?php
declare(strict_types=1);

namespace App\Domain;

use App\Core\ApiError;
use App\Core\Audit;
use App\Core\Clock;
use App\Core\Db;
use App\Core\Text;

/**
 * Nhận bản nháp từ dịch vụ Python (khóa có quyền drafts:write).
 * Mọi thứ vào trạng thái CHỜ DUYỆT; website không tự xuất bản nội dung AI (AT-09).
 * client_ref chống nhận trùng khi Python gửi lại.
 */
final class DraftInbox
{
    public static function receive(array $apiKey, array $items): array
    {
        if (count($items) > 200) throw new ApiError('PAYLOAD_TOO_LARGE', 'Tối đa 200 mục mỗi lần gửi.', 413);
        $results = [];
        foreach ($items as $item) {
            $ref = substr(preg_replace('/[^A-Za-z0-9_.:\-]/', '', (string)($item['client_ref'] ?? '')) ?? '', 0, 80);
            $kind = (string)($item['kind'] ?? '');
            if ($ref === '') {
                $results[] = ['client_ref' => null, 'status' => 'rejected', 'error' => 'Thiếu client_ref'];
                continue;
            }
            $dup = Db::one('SELECT status, result FROM sync_inbox WHERE api_key_id = :k AND client_ref = :r', ['k' => $apiKey['id'], 'r' => $ref]);
            if ($dup) {
                $results[] = ['client_ref' => $ref, 'status' => $dup['status'], 'duplicate' => true, 'result' => $dup['result']];
                continue;
            }
            try {
                $res = Db::tx(function () use ($apiKey, $ref, $kind, $item) {
                    $result = match ($kind) {
                        'blog', 'faq' => self::content($kind, (array)($item['data'] ?? [])),
                        'cross_sell'  => self::crossSell((array)($item['data'] ?? [])),
                        'care_list'   => self::careList((array)($item['data'] ?? [])),
                        default       => throw ApiError::validation(['kind' => 'Loại không hỗ trợ: ' . $kind]),
                    };
                    Db::insert('sync_inbox', ['api_key_id' => $apiKey['id'], 'client_ref' => $ref, 'kind' => $kind, 'status' => 'accepted', 'result' => mb_substr($result, 0, 500), 'created_at' => Clock::nowDb()]);
                    return $result;
                });
                $results[] = ['client_ref' => $ref, 'status' => 'accepted', 'result' => $res];
            } catch (ApiError $e) {
                Db::run('INSERT IGNORE INTO sync_inbox (api_key_id, client_ref, kind, status, result, created_at) VALUES (:k,:r,:kind,\'rejected\',:res,:t)',
                    ['k' => $apiKey['id'], 'r' => $ref, 'kind' => mb_substr($kind, 0, 32), 'res' => mb_substr($e->getMessage() . ' ' . json_enc($e->data), 0, 500), 't' => Clock::nowDb()]);
                $results[] = ['client_ref' => $ref, 'status' => 'rejected', 'error' => $e->getMessage(), 'details' => $e->data];
            }
        }
        return ['results' => $results];
    }

    private static function content(string $kind, array $d): string
    {
        $refs = (array)($d['source_refs'] ?? []);
        // Từ chối bản nháp dựa trên thông tin sản phẩm cũ hơn phiên bản hiện tại
        foreach ($refs as $r) {
            if (isset($r['product_id'], $r['info_version'])) {
                $cur = (int)Db::val('SELECT info_version FROM products WHERE id = :id', ['id' => (int)$r['product_id']]);
                if ($cur && $cur !== (int)$r['info_version']) {
                    throw new ApiError('SOURCE_OUTDATED', "Thông tin sản phẩm #{$r['product_id']} đã đổi (v$cur), bản nháp dựa trên v{$r['info_version']}.", 409);
                }
            }
        }
        $id = ContentService::create($kind, [
            'title' => $d['title'] ?? '', 'body' => $d['body'] ?? '', 'body_is_text' => !empty($d['body_is_text']),
            'meta_description' => $d['meta_description'] ?? null, 'keywords' => $d['keywords'] ?? null,
            'category_id' => $d['category_id'] ?? null, 'product_id' => $d['product_id'] ?? null,
            'source_refs' => $refs + ['generated_by' => mb_substr((string)($d['generated_by'] ?? 'python'), 0, 60)],
        ], 'ai', false);
        return "content:$id";
    }

    private static function crossSell(array $d): string
    {
        $p = (int)($d['product_id'] ?? 0);
        $r = (int)($d['related_product_id'] ?? 0);
        if ($p <= 0 || $r <= 0 || $p === $r || (int)Db::val('SELECT COUNT(*) FROM products WHERE id IN (:a,:b)', ['a' => $p, 'b' => $r]) !== 2) {
            throw ApiError::validation(['product_id' => 'Cặp sản phẩm không hợp lệ']);
        }
        $existing = Db::one('SELECT id, status FROM product_relations WHERE product_id = :p AND related_product_id = :r', ['p' => $p, 'r' => $r]);
        if ($existing) {
            return 'exists:' . $existing['status'];
        }
        $id = Db::insert('product_relations', [
            'product_id' => $p, 'related_product_id' => $r, 'source' => 'ai', 'status' => 'pending',
            'score' => isset($d['score']) ? round((float)$d['score'], 4) : null,
            'reason' => mb_substr((string)($d['reason'] ?? ''), 0, 300) ?: null, 'created_at' => Clock::nowDb(),
        ]);
        return "relation:$id";
    }

    /** Danh sách chăm sóc lại: Python chỉ biết customer_key; ánh xạ về khách tại máy chủ. */
    private static function careList(array $d): string
    {
        $batch = substr(preg_replace('/[^A-Za-z0-9_-]/', '', (string)($d['batch_id'] ?? '')) ?? '', 0, 40);
        if ($batch === '') throw ApiError::validation(['batch_id' => 'Bắt buộc']);
        $n = 0;
        foreach (array_slice((array)($d['entries'] ?? []), 0, 2000) as $e) {
            $cid = Db::val('SELECT id FROM customers WHERE customer_key = :k', ['k' => (string)($e['customer_key'] ?? '')]);
            $due = (string)($e['due_date'] ?? '');
            if (!$cid || !preg_match('/^\d{4}-\d{2}-\d{2}$/', $due)) continue;
            $n += Db::exec('INSERT IGNORE INTO care_suggestions (batch_id, customer_id, category_id, last_order_at, due_date, score, reason, status, created_at)
                            VALUES (:b,:c,:cat,:l,:d,:s,:r,\'pending\',:t)', [
                'b' => $batch, 'c' => $cid, 'cat' => isset($e['category_id']) ? (int)$e['category_id'] : null,
                'l' => $e['last_order_at'] ?? null, 'd' => $due, 's' => isset($e['score']) ? round((float)$e['score'], 4) : null,
                'r' => mb_substr((string)($e['reason'] ?? ''), 0, 300) ?: null, 't' => Clock::nowDb(),
            ]);
        }
        Audit::log('care.batch_received', 'care_batch', $batch, null, ['count' => $n], null, 'sync');
        return "care:$batch:$n";
    }
}
