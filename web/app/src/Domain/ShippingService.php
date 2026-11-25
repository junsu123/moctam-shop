<?php
declare(strict_types=1);

namespace App\Domain;

use App\Core\Clock;
use App\Core\Db;

final class ShippingService
{
    /** Danh sách tỉnh/thành đang phục vụ (cho ô chọn ở giỏ hàng). */
    public static function servedProvinces(): array
    {
        $list = [];
        foreach (Db::all('SELECT provinces FROM shipping_zones WHERE is_active = 1 ORDER BY sort_order') as $z) {
            foreach (json_dec($z['provinces']) as $p) {
                $list[$p] = true;
            }
        }
        $names = array_keys($list);
        sort($names, SORT_LOCALE_STRING);
        return $names;
    }

    public static function zoneFor(string $province): ?array
    {
        $province = trim($province);
        if ($province === '') {
            return null;
        }
        foreach (Db::all('SELECT * FROM shipping_zones WHERE is_active = 1 ORDER BY sort_order') as $z) {
            if (in_array($province, json_dec($z['provinces']), true)) {
                return $z;
            }
        }
        return null;
    }

    /** Biểu phí đang hiệu lực của vùng. */
    public static function activeRate(int $zoneId): ?array
    {
        return Db::one(
            'SELECT * FROM shipping_rates WHERE zone_id = :z AND effective_from <= :n AND (effective_to IS NULL OR effective_to > :n2) ORDER BY effective_from DESC, id DESC LIMIT 1',
            ['z' => $zoneId, 'n' => Clock::nowDb(), 'n2' => Clock::nowDb()]
        );
    }

    /** @return array{served:bool, zone_id:?int, zone_name:?string, rate_id:?int, fee:int, eta:?string, free_from:?int} */
    public static function quote(?string $province, int $goodsAfterDiscount): array
    {
        $zone = $province ? self::zoneFor($province) : null;
        $rate = $zone ? self::activeRate((int)$zone['id']) : null;
        if (!$zone || !$rate) {
            return ['served' => false, 'zone_id' => null, 'zone_name' => null, 'rate_id' => null, 'fee' => 0, 'eta' => null, 'free_from' => null, 'province' => $province];
        }
        $fee = (int)$rate['fee'];
        if ($rate['free_from'] !== null && $goodsAfterDiscount >= (int)$rate['free_from']) {
            $fee = 0;
        }
        return [
            'served'    => true,
            'zone_id'   => (int)$zone['id'],
            'zone_name' => $zone['name'],
            'rate_id'   => (int)$rate['id'],
            'fee'       => $fee,
            'eta'       => $zone['eta_text'],
            'free_from' => $rate['free_from'] === null ? null : (int)$rate['free_from'],
            'province'  => $province,
        ];
    }
}
