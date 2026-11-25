<?php
declare(strict_types=1);

namespace App\Domain;

use App\Core\Settings;

/**
 * Sinh chuỗi VietQR (chuẩn EMVCo của NAPAS) ngay trên máy chủ, không phụ thuộc dịch vụ ngoài.
 * Trình duyệt vẽ QR từ chuỗi này (assets/js/qrcode.js).
 */
final class VietQr
{
    public static function payload(string $bankBin, string $accountNo, int $amount, string $content): string
    {
        $merchant = self::tlv('00', 'A000000727')
            . self::tlv('01', self::tlv('00', $bankBin) . self::tlv('01', $accountNo))
            . self::tlv('02', 'QRIBFTTA');
        $content = preg_replace('/[^A-Za-z0-9 ]/', '', $content) ?? '';
        $data = self::tlv('00', '01')
            . self::tlv('01', '12')
            . self::tlv('38', $merchant)
            . self::tlv('53', '704')
            . self::tlv('54', (string)$amount)
            . self::tlv('58', 'VN')
            . self::tlv('62', self::tlv('08', substr($content, 0, 25)))
            . '6304';
        return $data . self::crc16($data);
    }

    public static function instructions(int $amount, string $content): array
    {
        $bin = Settings::get('vietqr_bank_bin');
        $acc = Settings::get('vietqr_account_no');
        return [
            'bank_bin'     => $bin,
            'bank_name'    => Settings::get('vietqr_bank_name'),
            'account_no'   => $acc,
            'account_name' => Settings::get('vietqr_account_name'),
            'amount'       => $amount,
            'content'      => $content,
            'qr_payload'   => self::payload($bin, $acc, $amount, $content),
        ];
    }

    private static function tlv(string $id, string $value): string
    {
        return $id . str_pad((string)strlen($value), 2, '0', STR_PAD_LEFT) . $value;
    }

    /** CRC-16/CCITT-FALSE (poly 0x1021, init 0xFFFF). */
    public static function crc16(string $data): string
    {
        $crc = 0xFFFF;
        $len = strlen($data);
        for ($i = 0; $i < $len; $i++) {
            $crc ^= ord($data[$i]) << 8;
            for ($j = 0; $j < 8; $j++) {
                $crc = ($crc & 0x8000) ? (($crc << 1) ^ 0x1021) : ($crc << 1);
                $crc &= 0xFFFF;
            }
        }
        return strtoupper(str_pad(dechex($crc), 4, '0', STR_PAD_LEFT));
    }
}
