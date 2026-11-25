<?php
declare(strict_types=1);

namespace App\Core;

final class Settings
{
    private static ?array $cache = null;

    public static function all(): array
    {
        if (self::$cache === null) {
            self::$cache = [];
            foreach (Db::all('SELECT `key`, `value` FROM settings') as $r) {
                self::$cache[$r['key']] = $r['value'];
            }
        }
        return self::$cache;
    }

    public static function get(string $key, string $default = ''): string
    {
        return self::all()[$key] ?? $default;
    }

    public static function int(string $key, int $default): int
    {
        $v = self::get($key, '');
        return $v === '' ? $default : (int)$v;
    }

    public static function set(string $key, string $value): void
    {
        Db::run('INSERT INTO settings (`key`,`value`,updated_at) VALUES (:k,:v,:t) ON DUPLICATE KEY UPDATE `value`=VALUES(`value`), updated_at=VALUES(updated_at)', [
            'k' => $key, 'v' => $value, 't' => Clock::nowDb(),
        ]);
        self::$cache = null;
    }

    public static function flush(): void
    {
        self::$cache = null;
    }
}
