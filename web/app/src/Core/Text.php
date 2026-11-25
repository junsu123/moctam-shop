<?php
declare(strict_types=1);

namespace App\Core;

/** Xử lý chuỗi tiếng Việt: bỏ dấu để tìm kiếm có dấu/không dấu (FR-01). */
final class Text
{
    private const MAP = [
        'à'=>'a','á'=>'a','ạ'=>'a','ả'=>'a','ã'=>'a','â'=>'a','ầ'=>'a','ấ'=>'a','ậ'=>'a','ẩ'=>'a','ẫ'=>'a','ă'=>'a','ằ'=>'a','ắ'=>'a','ặ'=>'a','ẳ'=>'a','ẵ'=>'a',
        'è'=>'e','é'=>'e','ẹ'=>'e','ẻ'=>'e','ẽ'=>'e','ê'=>'e','ề'=>'e','ế'=>'e','ệ'=>'e','ể'=>'e','ễ'=>'e',
        'ì'=>'i','í'=>'i','ị'=>'i','ỉ'=>'i','ĩ'=>'i',
        'ò'=>'o','ó'=>'o','ọ'=>'o','ỏ'=>'o','õ'=>'o','ô'=>'o','ồ'=>'o','ố'=>'o','ộ'=>'o','ổ'=>'o','ỗ'=>'o','ơ'=>'o','ờ'=>'o','ớ'=>'o','ợ'=>'o','ở'=>'o','ỡ'=>'o',
        'ù'=>'u','ú'=>'u','ụ'=>'u','ủ'=>'u','ũ'=>'u','ư'=>'u','ừ'=>'u','ứ'=>'u','ự'=>'u','ử'=>'u','ữ'=>'u',
        'ỳ'=>'y','ý'=>'y','ỵ'=>'y','ỷ'=>'y','ỹ'=>'y','đ'=>'d',
    ];

    public static function fold(string $s): string
    {
        if (class_exists(\Normalizer::class)) {
            $s = \Normalizer::normalize($s, \Normalizer::FORM_C) ?: $s;
        }
        $s = mb_strtolower($s, 'UTF-8');
        $s = strtr($s, self::MAP);
        $s = preg_replace('/[^a-z0-9]+/u', ' ', $s) ?? '';
        return trim(preg_replace('/\s+/', ' ', $s) ?? '');
    }

    /** @return string[] */
    public static function tokens(string $s): array
    {
        $f = self::fold($s);
        return $f === '' ? [] : explode(' ', $f);
    }

    public static function slug(string $s): string
    {
        $slug = str_replace(' ', '-', self::fold($s));
        return $slug !== '' ? substr($slug, 0, 200) : 'muc-' . bin2hex(random_bytes(3));
    }

    public static function excerpt(string $html, int $len = 160): string
    {
        $t = trim(preg_replace('/\s+/u', ' ', html_entity_decode(strip_tags($html), ENT_QUOTES, 'UTF-8')) ?? '');
        return mb_strlen($t) > $len ? rtrim(mb_substr($t, 0, $len - 1)) . '…' : $t;
    }

    /** Chuẩn hóa SĐT Việt Nam về dạng 0xxxxxxxxx; null nếu không hợp lệ. */
    public static function normalizePhone(string $p): ?string
    {
        $p = preg_replace('/[\s.\-()]/', '', $p) ?? '';
        if (str_starts_with($p, '+84')) {
            $p = '0' . substr($p, 3);
        } elseif (str_starts_with($p, '84') && strlen($p) === 11) {
            $p = '0' . substr($p, 2);
        }
        return preg_match('/^0(3|5|7|8|9)\d{8}$/', $p) ? $p : null;
    }

    public static function maskPhone(string $p): string
    {
        return strlen($p) >= 7 ? substr($p, 0, 3) . '****' . substr($p, -3) : '***';
    }
}
