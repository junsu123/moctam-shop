<?php
declare(strict_types=1);

namespace App\Domain;

use App\Core\Audit;
use App\Core\Clock;
use App\Core\Db;
use App\Core\Html;
use App\Core\Text;

/**
 * Trang pháp lý đi kèm mã nguồn (app/content/legal/*.html) và biến {{...}} lấy từ Cấu hình.
 *
 * Cài đặt / cập nhật (gọi từ migration):
 *   - Chưa có trang            → tạo và xuất bản.
 *   - Trang chỉ có bản mẫu / bản kèm mã nguồn (chưa nhân viên nào sửa) → thêm phiên bản mới và xuất bản.
 *   - Xưởng đã tự sửa trang     → KHÔNG ghi đè: thêm phiên bản mới ở trạng thái chờ duyệt.
 */
final class LegalPages
{
    public const PAGES = [
        'bao-mat' => ['title' => 'Chính sách bảo mật thông tin', 'file' => 'chinh-sach-bao-mat-thong-tin.html',
            'meta' => 'Cách xưởng thu thập, sử dụng, lưu trữ và bảo vệ thông tin cá nhân của khách hàng; quyền của bạn và cách liên hệ.'],
        'dieu-khoan-su-dung' => ['title' => 'Điều khoản sử dụng', 'file' => 'dieu-khoan-su-dung.html',
            'meta' => 'Điều khoản sử dụng website và mua hàng: đặt hàng, giá, ưu đãi, thanh toán, giao nhận, đổi trả, khiếu nại.'],
    ];

    /** Biến dùng được trong trang nội dung: khóa => [nhãn khi trống, nguồn] */
    public const PLACEHOLDERS = [
        'store_name' => 'Tên cửa hàng', 'business_name' => 'Tên hộ kinh doanh / doanh nghiệp',
        'business_reg_no' => 'Số đăng ký kinh doanh / mã số thuế', 'business_reg_info' => 'Ngày cấp, nơi cấp',
        'representative' => 'Người đại diện', 'address' => 'Địa chỉ', 'hotline' => 'Hotline', 'zalo' => 'Zalo',
        'support_email' => 'Email hỗ trợ', 'privacy_email' => 'Email liên hệ dữ liệu cá nhân',
        'hosting_provider' => 'Nhà cung cấp máy chủ', 'server_location' => 'Nơi đặt máy chủ',
        'hold_hours_vietqr' => 'Thời hạn giữ hàng VietQR', 'hold_hours_cod' => 'Thời hạn chờ xác nhận COD',
        'quote_ttl_minutes' => 'Hiệu lực báo giá', 'chat_log_days' => 'Thời hạn lưu câu hỏi chat',
        'sync_event_retention_days' => 'Thời hạn lưu dữ liệu đồng bộ', 'complaint_reply_days' => 'Thời hạn phản hồi khiếu nại',
        'site_domain' => 'Tên miền',
    ];

    public static function install(): array
    {
        $result = [];
        foreach (self::PAGES as $slug => $p) {
            $body = Html::sanitize((string)file_get_contents(APP_ROOT . '/content/legal/' . $p['file']));
            $now = Clock::nowDb();
            $c = Db::one("SELECT * FROM contents WHERE kind = 'page' AND slug = :s", ['s' => $slug]);
            if (!$c) {
                $id = Db::insert('contents', ['kind' => 'page', 'slug' => $slug, 'status' => 'draft', 'source' => 'staff', 'created_at' => $now, 'updated_at' => $now]);
                $vid = self::version($id, $p, $body, 'Tạo từ mẫu kèm mã nguồn');
                self::publish($id, $vid, $p, $body);
                $result[$slug] = 'created';
                continue;
            }
            $published = Db::one('SELECT body FROM content_versions WHERE id = :v', ['v' => (int)$c['published_version_id']]);
            // Phiên bản do nhân viên tạo trong Quản trị có created_by; bản mẫu/bản kèm mã nguồn thì không
            $editedVersions = (int)Db::val('SELECT COUNT(*) FROM content_versions WHERE content_id = :c AND created_by IS NOT NULL', ['c' => $c['id']]);
            if ($published && trim($published['body']) === trim($body)) {
                $result[$slug] = 'unchanged';
            } elseif ($editedVersions === 0) {
                $vid = self::version((int)$c['id'], $p, $body, 'Thay bản mẫu bằng nội dung đầy đủ');
                self::publish((int)$c['id'], $vid, $p, $body);
                $result[$slug] = 'updated';
            } else {
                // Xưởng đã tự sửa: giữ bản đang công khai, đưa bản mới vào chờ duyệt để so sánh
                $vid = self::version((int)$c['id'], $p, $body, 'Bản cập nhật kèm mã nguồn — so sánh với bản đang công khai trước khi xuất bản');
                Db::update('contents', ['current_version_id' => $vid, 'status' => $c['status'] === 'published' ? 'published' : 'pending_review', 'updated_at' => $now], 'id = :id', ['id' => $c['id']]);
                $result[$slug] = 'new_version_pending';
            }
        }
        Audit::log('legal_pages.install', 'content', 'legal', null, $result, null, 'system');
        return $result;
    }

    private static function version(int $contentId, array $p, string $body, string $note): int
    {
        $no = (int)Db::val('SELECT COALESCE(MAX(version_no),0)+1 FROM content_versions WHERE content_id = :c', ['c' => $contentId]);
        $vid = Db::insert('content_versions', [
            'content_id' => $contentId, 'version_no' => $no, 'title' => $p['title'], 'meta_description' => $p['meta'], 'body' => $body,
            'keywords' => null, 'source_refs' => null, 'created_by' => null, 'created_source' => 'staff', 'review_note' => $note, 'created_at' => Clock::nowDb(),
        ]);
        Db::update('contents', ['current_version_id' => $vid], 'id = :id', ['id' => $contentId]);
        return $vid;
    }

    private static function publish(int $id, int $vid, array $p, string $body): void
    {
        $now = Clock::nowDb();
        Db::update('contents', [
            'status' => 'published', 'published_version_id' => $vid, 'current_version_id' => $vid, 'pub_title' => $p['title'],
            'pub_meta_description' => $p['meta'], 'pub_body' => $body, 'pub_search_text' => Text::fold($p['title'] . ' ' . Text::excerpt($body, 600)),
            'published_at' => $now, 'updated_at' => $now,
        ], 'id = :id', ['id' => $id]);
    }

    /** Giá trị mặc định lúc cài — chưa phải thông tin thật của xưởng. */
    private const INSTALL_DEFAULTS = ['0900 000 000', '0900000000', 'hotro@example.vn', '0000000000'];

    public static function isUnset(string $v): bool
    {
        $v = trim($v);
        return $v === '' || in_array($v, self::INSTALL_DEFAULTS, true) || str_contains($v, 'cập nhật trong Cấu hình');
    }

    /** Thay {{biến}} bằng giá trị Cấu hình (đã mã hóa HTML). Biến trống → nhãn "[chưa cập nhật: …]" dễ thấy. */
    public static function render(string $html): string
    {
        return (string)preg_replace_callback('/\{\{\s*([a-z_]+)\s*\}\}/', function ($m) {
            $key = $m[1];
            if (!isset(self::PLACEHOLDERS[$key])) {
                return $m[0];
            }
            $val = match ($key) {
                'site_domain' => (string)(parse_url((string)config('base_url'), PHP_URL_HOST) ?: ''),
                'privacy_email' => setting('privacy_email') ?: setting('support_email'),
                'business_name' => setting('business_name') ?: setting('store_name'),
                default => setting($key),
            };
            $val = trim($val);
            if (self::isUnset($val)) {
                return '<span class="rounded bg-turmeric-light px-1 text-coffee">[chưa cập nhật: ' . e(mb_strtolower(self::PLACEHOLDERS[$key])) . ']</span>';
            }
            return e($val);
        }, $html);
    }

    /** Các mục pháp lý còn trống — hiển thị cảnh báo ở trang Giám sát. */
    public static function missingSettings(): array
    {
        $out = [];
        foreach (['business_name', 'business_reg_no', 'representative', 'address', 'hotline', 'support_email', 'server_location'] as $k) {
            if (self::isUnset(setting($k))) $out[] = self::PLACEHOLDERS[$k];
        }
        return $out;
    }
}
