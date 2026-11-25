<?php
declare(strict_types=1);

namespace App\Core;

final class RateLimiter
{
    /** Cửa sổ cố định đơn giản lưu trong MySQL (phù hợp hosting chia sẻ). */
    public static function hit(string $bucket, int $max, int $windowSeconds): void
    {
        if (PHP_SAPI === 'cli' || config('rate_limit', true) === false) {
            return; // tắt chỉ khi đo tải trên môi trường thử
        }
        $key = substr($bucket . ':' . hash('sha256', client_ip()), 0, 120);
        $now = Clock::now();
        $row = Db::one('SELECT hits, window_start FROM rate_limits WHERE bucket = :b', ['b' => $key]);
        if (!$row || strtotime($row['window_start'] . ' UTC') + $windowSeconds < $now->getTimestamp()) {
            Db::run('REPLACE INTO rate_limits (bucket, hits, window_start) VALUES (:b, 1, :t)', ['b' => $key, 't' => Clock::nowDb()]);
            return;
        }
        if ((int)$row['hits'] >= $max) {
            throw new ApiError('RATE_LIMITED', 'Bạn thao tác quá nhanh, vui lòng thử lại sau ít phút.', 429);
        }
        Db::exec('UPDATE rate_limits SET hits = hits + 1 WHERE bucket = :b', ['b' => $key]);
    }
}
