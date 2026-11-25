<?php
declare(strict_types=1);

namespace App\Domain;

use App\Core\Text;

/**
 * BM25 chuẩn hóa về [0,1) — CÙNG thuật toán với ai/xuong_ai/memory.py để ngưỡng
 * hiệu chỉnh bằng Python dùng được trực tiếp cho chat trên website.
 *   norm = Σ idf(t)·tf(k1+1)/(tf + k1(1−b+b·|d|/avgdl))  /  Σ idf(t)·(k1+1)
 */
final class Bm25
{
    public const K1 = 1.2;
    public const B = 0.75;

    private const STOP = ['a', 'ah', 'oi', 'la', 'thi', 'ma', 'va', 'voi', 'cua', 'cho', 'toi', 'minh', 'em', 'anh', 'chi',
        'ban', 'shop', 'nhe', 'nha', 'vay', 'the', 'nao', 'gi', 'sao', 'hay', 'cac', 'mot', 'u', 'duoc', 'ad', 'admin', 'xin', 'hoi', 'cam', 'on', 'ah', 'ha', 'ne'];
    private const ALIAS = ['ko' => 'khong', 'k' => 'khong', 'hok' => 'khong', 'hong' => 'khong', 'kg' => 'khong', 'dc' => 'duoc', 'sp' => 'san pham', 'ship' => 'giao', 'cf' => 'ca phe', 'cafe' => 'ca phe', 'coffee' => 'ca phe'];

    /** @return string[] unigram + bigram */
    public static function terms(string $text): array
    {
        $raw = [];
        foreach (Text::tokens($text) as $t) {
            foreach (explode(' ', self::ALIAS[$t] ?? $t) as $x) {
                $raw[] = $x;
            }
        }
        $toks = array_values(array_filter($raw, fn($t) => !in_array($t, self::STOP, true)));
        $out = $toks;
        for ($i = 0; $i + 1 < count($toks); $i++) {
            $out[] = $toks[$i] . '_' . $toks[$i + 1];
        }
        return $out;
    }

    /**
     * @param array<int|string,string> $docs id => text
     * @return array<int|string,float> id => điểm chuẩn hóa, giảm dần
     */
    public static function rank(string $query, array $docs): array
    {
        $q = array_unique(self::terms($query));
        if (!$q || !$docs) return [];
        $tfs = [];
        $df = [];
        $lenSum = 0;
        foreach ($docs as $id => $text) {
            $terms = self::terms($text);
            $tf = array_count_values($terms);
            $tfs[$id] = [$tf, count($terms)];
            $lenSum += count($terms);
            foreach (array_keys($tf) as $t) {
                $df[$t] = ($df[$t] ?? 0) + 1;
            }
        }
        $n = count($docs);
        $avg = max(1.0, $lenSum / $n);
        $idf = [];
        $max = 0.0;
        foreach ($q as $t) {
            $d = $df[$t] ?? 0;
            $idf[$t] = log(1 + ($n - $d + 0.5) / ($d + 0.5));
            $max += $idf[$t] * (self::K1 + 1);
        }
        $scores = [];
        foreach ($tfs as $id => [$tf, $len]) {
            $s = 0.0;
            foreach ($q as $t) {
                $f = $tf[$t] ?? 0;
                if ($f > 0) {
                    $s += $idf[$t] * $f * (self::K1 + 1) / ($f + self::K1 * (1 - self::B + self::B * $len / $avg));
                }
            }
            if ($s > 0) $scores[$id] = $max > 0 ? $s / $max : 0.0;
        }
        arsort($scores);
        return $scores;
    }
}
