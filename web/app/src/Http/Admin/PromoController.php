<?php
declare(strict_types=1);

namespace App\Http\Admin;

use App\Core\ApiError;
use App\Core\Audit;
use App\Core\Clock;
use App\Core\Db;
use App\Domain\PromotionService;

final class PromoController extends Base
{
    // ------------------------------------------------------------ vùng giao
    public function shipping(): string
    {
        $this->need('shipping.manage');
        $zones = Db::all('SELECT * FROM shipping_zones ORDER BY sort_order, id');
        foreach ($zones as &$z) {
            $z['rates'] = Db::all('SELECT * FROM shipping_rates WHERE zone_id = :z ORDER BY effective_from DESC, id DESC LIMIT 10', ['z' => $z['id']]);
            $z['active'] = \App\Domain\ShippingService::activeRate((int)$z['id']);
        }
        return $this->view('shipping', ['title' => 'Vùng giao & biểu phí', 'zones' => $zones]);
    }

    public function saveZone(): void
    {
        $this->need('shipping.manage');
        $id = $this->int('id');
        $provs = array_values(array_unique(array_filter(array_map('trim', preg_split('/[\n,;]+/', $this->str('provinces')) ?: []))));
        $data = ['name' => mb_substr($this->str('name'), 0, 120), 'provinces' => json_enc($provs), 'eta_text' => mb_substr($this->str('eta_text'), 0, 120) ?: null,
            'is_active' => $this->str('is_active') ? 1 : 0, 'sort_order' => $this->int('sort_order')];
        if ($data['name'] === '' || !$provs) throw ApiError::validation(['name' => $data['name'] === '' ? 'Bắt buộc' : null, 'provinces' => !$provs ? 'Nhập ít nhất một tỉnh/thành' : null]);
        // Một tỉnh chỉ thuộc một vùng đang bật
        foreach (Db::all('SELECT id, name, provinces FROM shipping_zones WHERE is_active = 1 AND id <> :id', ['id' => $id]) as $z) {
            $dup = array_intersect($provs, json_dec($z['provinces']));
            if ($dup && $data['is_active']) throw ApiError::validation(['provinces' => implode(', ', $dup) . ' đã thuộc vùng "' . $z['name'] . '"']);
        }
        if ($id) {
            $before = Db::one('SELECT * FROM shipping_zones WHERE id = :id', ['id' => $id]);
            Db::update('shipping_zones', $data, 'id = :id', ['id' => $id]);
            Audit::log('zone.update', 'shipping_zone', (string)$id, $before, $data);
        } else {
            $id = Db::insert('shipping_zones', $data);
            Audit::log('zone.create', 'shipping_zone', (string)$id, null, $data);
        }
        $this->back('Đã lưu vùng giao. Nhớ thêm biểu phí nếu vùng chưa có.');
    }

    /** Biểu phí mới có hiệu lực từ thời điểm chọn; đơn cũ giữ phí đã chụp. */
    public function addRate(): void
    {
        $this->need('shipping.manage');
        $zone = $this->int('zone_id');
        $from = Clock::fromLocalInput($this->str('effective_from')) ?? Clock::nowDb();
        $fee = $this->int('fee', -1);
        if ($fee < 0) throw ApiError::validation(['fee' => 'Nhập phí giao (0 nếu miễn phí)']);
        Db::tx(function () use ($zone, $from, $fee) {
            // Đóng biểu phí đang mở trước đó tại mốc mới
            Db::exec('UPDATE shipping_rates SET effective_to = :f WHERE zone_id = :z AND effective_to IS NULL AND effective_from < :f2', ['f' => $from, 'f2' => $from, 'z' => $zone]);
            $id = Db::insert('shipping_rates', ['zone_id' => $zone, 'fee' => $fee, 'free_from' => $this->str('free_from') === '' ? null : $this->int('free_from'), 'effective_from' => $from, 'created_at' => Clock::nowDb()]);
            Audit::log('rate.create', 'shipping_rate', (string)$id, null, ['zone' => $zone, 'fee' => $fee, 'from' => $from]);
        });
        $this->back('Đã thêm biểu phí.');
    }

    // ------------------------------------------------------------ voucher
    public function vouchers(): string
    {
        $this->need('promo.manage');
        return $this->view('vouchers', ['title' => 'Voucher', 'rows' => Db::all('SELECT * FROM vouchers ORDER BY is_active DESC, ends_at DESC')]);
    }

    public function voucherForm(string $id): string
    {
        $this->need('promo.manage');
        $v = $id === 'new' ? null : Db::one('SELECT * FROM vouchers WHERE id = :id', ['id' => (int)$id]);
        if ($id !== 'new' && !$v) throw ApiError::notFound();
        return $this->view('voucher_form', [
            'title' => $v ? 'Voucher ' . $v['code'] : 'Tạo voucher', 'v' => $v,
            'cats' => Db::all('SELECT id, name FROM categories ORDER BY sort_order'),
            'products' => Db::all("SELECT id, name FROM products WHERE status = 'active' ORDER BY name"),
            'usages' => $v ? Db::all('SELECT vu.*, o.code FROM voucher_usages vu JOIN orders o ON o.id = vu.order_id WHERE vu.voucher_id = :v ORDER BY vu.id DESC LIMIT 50', ['v' => $v['id']]) : [],
        ]);
    }

    public function saveVoucher(): void
    {
        $id = $this->int('id') ?: null;
        $_POST['scope_ids'] = $_POST['scope_type'] === 'category' ? ($_POST['scope_cat'] ?? []) : ($_POST['scope_type'] === 'product' ? ($_POST['scope_prod'] ?? []) : []);
        $new = PromotionService::saveVoucher($id, $_POST);
        $this->back('Đã lưu voucher.', '/admin/vouchers/' . $new);
    }

    // ------------------------------------------------------------ flash sale
    public function flashSales(): string
    {
        $this->need('promo.manage');
        return $this->view('flash_sales', ['title' => 'Flash Sale', 'rows' => Db::all('SELECT f.*, (SELECT COUNT(*) FROM flash_sale_items i WHERE i.flash_sale_id = f.id) AS n FROM flash_sales f ORDER BY f.starts_at DESC')]);
    }

    public function flashForm(string $id): string
    {
        $this->need('promo.manage');
        $f = $id === 'new' ? null : Db::one('SELECT * FROM flash_sales WHERE id = :id', ['id' => (int)$id]);
        if ($id !== 'new' && !$f) throw ApiError::notFound();
        return $this->view('flash_form', [
            'title' => $f ? $f['name'] : 'Tạo Flash Sale', 'fs' => $f,
            'items' => $f ? Db::all('SELECT fi.*, s.sku_code, s.price FROM flash_sale_items fi JOIN skus s ON s.id = fi.sku_id WHERE fi.flash_sale_id = :id', ['id' => $f['id']]) : [],
            'skus' => Db::all("SELECT s.id, s.sku_code, s.variant_label, s.price, p.name FROM skus s JOIN products p ON p.id = s.product_id WHERE s.status = 'active' AND p.status = 'active' ORDER BY p.name, s.sort_order"),
        ]);
    }

    public function saveFlash(): void
    {
        $items = [];
        foreach ((array)($_POST['item_sku'] ?? []) as $i => $sku) {
            if ((int)$sku > 0) $items[(int)$sku] = (int)($_POST['item_price'][$i] ?? 0);
        }
        $id = PromotionService::saveFlashSale($this->int('id') ?: null, $_POST, $items);
        $this->back('Đã lưu Flash Sale.', '/admin/flash-sales/' . $id);
    }
}
