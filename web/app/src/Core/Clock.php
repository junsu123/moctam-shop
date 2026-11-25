<?php
declare(strict_types=1);

namespace App\Core;

use DateTimeImmutable;
use DateTimeZone;

/** Đồng hồ UTC có thể đặt lại khi kiểm thử. */
final class Clock
{
    private static ?DateTimeImmutable $fixed = null;
    public const LOCAL_TZ = 'Asia/Ho_Chi_Minh';

    public static function now(): DateTimeImmutable
    {
        return self::$fixed ?? new DateTimeImmutable('now', new DateTimeZone('UTC'));
    }

    public static function set(?DateTimeImmutable $t): void
    {
        self::$fixed = $t?->setTimezone(new DateTimeZone('UTC'));
    }

    public static function nowDb(): string
    {
        return self::now()->format('Y-m-d H:i:s');
    }

    public static function db(DateTimeImmutable $t): string
    {
        return $t->setTimezone(new DateTimeZone('UTC'))->format('Y-m-d H:i:s');
    }

    public static function toLocal(string $utc): DateTimeImmutable
    {
        return (new DateTimeImmutable($utc, new DateTimeZone('UTC')))->setTimezone(new DateTimeZone(self::LOCAL_TZ));
    }

    /** Chuyển giá trị ô datetime-local (giờ VN) sang UTC để lưu. */
    public static function fromLocalInput(string $local): ?string
    {
        $local = trim($local);
        if ($local === '') {
            return null;
        }
        try {
            $t = new DateTimeImmutable($local, new DateTimeZone(self::LOCAL_TZ));
        } catch (\Exception) {
            return null;
        }
        return self::db($t);
    }

    public static function toLocalInput(?string $utc): string
    {
        return $utc ? self::toLocal($utc)->format('Y-m-d\TH:i') : '';
    }
}
