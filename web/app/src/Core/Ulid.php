<?php
declare(strict_types=1);

namespace App\Core;

final class Ulid
{
    private const ALPHABET = '0123456789ABCDEFGHJKMNPQRSTVWXYZ';

    public static function generate(): string
    {
        $time = (int)(microtime(true) * 1000);
        $t = '';
        for ($i = 0; $i < 10; $i++) {
            $t = self::ALPHABET[$time % 32] . $t;
            $time = intdiv($time, 32);
        }
        $r = '';
        $bytes = random_bytes(16);
        for ($i = 0; $i < 16; $i++) {
            $r .= self::ALPHABET[ord($bytes[$i]) % 32];
        }
        return $t . $r;
    }

    public static function code(int $len): string
    {
        $s = '';
        $alpha = '23456789ABCDEFGHJKMNPQRSTUVWXYZ';
        for ($i = 0; $i < $len; $i++) {
            $s .= $alpha[random_int(0, strlen($alpha) - 1)];
        }
        return $s;
    }
}
