<?php
declare(strict_types=1);

namespace App\Http\Admin;

use App\Core\Db;
use App\Domain\InventoryService;

final class InventoryController extends Base
{
    public function index(): string
    {
        $this->need('inventory.manage');
        $where = ["1=1"];
        $p = [];
        if (($q = $this->str('q')) !== '') {
            $where[] = '(s.sku_code LIKE :q OR p.search_text LIKE :q2)';
            $p += ['q' => '%' . strtoupper($q) . '%', 'q2' => '%' . \App\Core\Text::fold($q) . '%'];
        }
        if ($this->str('low')) $where[] = 'i.on_hand - i.reserved <= 10';
        if (!$this->str('all')) $where[] = "s.status = 'active'";
        $rows = Db::all('SELECT s.id, s.sku_code, s.variant_label, s.status, s.price, p.name, p.id AS product_id, i.on_hand, i.reserved, i.on_hand - i.reserved AS available, i.updated_at
                           FROM skus s JOIN products p ON p.id = s.product_id JOIN inventory i ON i.sku_id = s.id WHERE ' . implode(' AND ', $where) . ' ORDER BY p.name, s.sort_order', $p);
        return $this->view('inventory', ['title' => 'Tồn kho', 'rows' => $rows, 'f' => $_GET]);
    }

    public function adjust(string $sku): never
    {
        $type = $this->str('type') === 'receive' ? 'receive' : 'adjust';
        $delta = $this->int('delta');
        InventoryService::adjust((int)$sku, $delta, $type, $this->str('reason'));
        $this->back(($type === 'receive' ? 'Đã nhập kho ' : 'Đã điều chỉnh ') . sprintf('%+d', $delta) . '.');
    }

    public function movements(): string
    {
        $this->need('inventory.manage');
        $where = ['1=1'];
        $p = [];
        if (($sku = $this->str('sku')) !== '') { $where[] = 's.sku_code = :s'; $p['s'] = strtoupper($sku); }
        if (($code = $this->str('order')) !== '') { $where[] = 'o.code = :o'; $p['o'] = strtoupper($code); }
        if (($t = $this->str('type')) !== '') { $where[] = 'm.type = :t'; $p['t'] = $t; }
        $page = max(1, $this->int('page', 1));
        $total = (int)Db::val('SELECT COUNT(*) FROM inventory_movements m JOIN skus s ON s.id = m.sku_id LEFT JOIN orders o ON o.id = m.order_id WHERE ' . implode(' AND ', $where), $p);
        $rows = Db::all('SELECT m.*, s.sku_code, o.code AS order_code, o.id AS oid, u.full_name FROM inventory_movements m JOIN skus s ON s.id = m.sku_id LEFT JOIN orders o ON o.id = m.order_id LEFT JOIN users u ON u.id = m.user_id
                          WHERE ' . implode(' AND ', $where) . ' ORDER BY m.id DESC LIMIT 50 OFFSET :off', $p + ['off' => ($page - 1) * 50]);
        return $this->view('movements', ['title' => 'Biến động kho', 'rows' => $rows, 'f' => $_GET, 'page' => $page, 'pages' => (int)ceil($total / 50)]);
    }
}
