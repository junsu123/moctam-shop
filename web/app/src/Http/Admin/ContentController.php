<?php
declare(strict_types=1);

namespace App\Http\Admin;

use App\Core\ApiError;
use App\Core\Db;
use App\Domain\ContentService;

final class ContentController extends Base
{
    public function index(): string
    {
        $this->need('content.edit');
        $kind = in_array($k = $this->str('kind', 'blog'), ['blog', 'faq', 'page'], true) ? $k : 'blog';
        $st = $this->str('status');
        $where = 'c.kind = :k' . (isset(ContentService::STATUS_LABELS[$st]) ? ' AND c.status = :s' : '');
        $p = ['k' => $kind] + (isset(ContentService::STATUS_LABELS[$st]) ? ['s' => $st] : []);
        $rows = Db::all("SELECT c.*, v.title AS cur_title, v.version_no, v.created_source FROM contents c LEFT JOIN content_versions v ON v.id = c.current_version_id WHERE $where ORDER BY FIELD(c.status,'pending_review','draft','published','unpublished'), c.updated_at DESC", $p);
        $counts = [];
        foreach (Db::all('SELECT status, COUNT(*) n FROM contents WHERE kind = :k GROUP BY status', ['k' => $kind]) as $r) $counts[$r['status']] = (int)$r['n'];
        return $this->view('contents', ['title' => ContentService::KIND_LABELS[$kind], 'kind' => $kind, 'rows' => $rows, 'st' => $st, 'counts' => $counts]);
    }

    public function create(): string
    {
        $this->need('content.edit');
        $kind = in_array($k = $this->str('kind', 'blog'), ['blog', 'faq', 'page'], true) ? $k : 'blog';
        return $this->form(null, $kind);
    }

    public function edit(string $id): string
    {
        $this->need('content.edit');
        return $this->form((int)$id, null);
    }

    private function form(?int $id, ?string $kind): string
    {
        $c = $id ? Db::one('SELECT * FROM contents WHERE id = :id', ['id' => $id]) : null;
        if ($id && !$c) throw ApiError::notFound();
        $versions = $id ? Db::all('SELECT v.*, u.full_name, r.full_name AS reviewer FROM content_versions v LEFT JOIN users u ON u.id = v.created_by LEFT JOIN users r ON r.id = v.reviewed_by WHERE v.content_id = :id ORDER BY v.version_no DESC', ['id' => $id]) : [];
        $show = $versions[0] ?? null;
        if ($id && ($vid = $this->int('version'))) {
            foreach ($versions as $v) if ((int)$v['id'] === $vid) $show = $v;
        }
        return $this->view('content_form', [
            'title' => $c ? ($show['title'] ?? 'Nội dung') : 'Tạo ' . mb_strtolower(ContentService::KIND_LABELS[$kind]),
            'c' => $c, 'kind' => $c['kind'] ?? $kind, 'versions' => $versions, 'cur' => $show,
            'cats' => Db::all('SELECT id, name FROM categories ORDER BY sort_order'),
            'products' => Db::all("SELECT id, name, info_version FROM products WHERE status <> 'discontinued' ORDER BY name"),
        ]);
    }

    public function save(): void
    {
        $id = $this->int('id');
        $submit = $this->str('action') === 'submit';
        if ($id) {
            ContentService::saveVersion($id, $_POST, $submit);
            if ($this->str('action') === 'publish') ContentService::publish($id);
        } else {
            $id = ContentService::create($this->str('kind'), $_POST);
            if ($submit) ContentService::submit($id);
            if ($this->str('action') === 'publish') ContentService::publish($id);
        }
        $this->back($this->str('action') === 'publish' ? 'Đã lưu và xuất bản.' : ($submit ? 'Đã lưu và gửi duyệt.' : 'Đã lưu phiên bản mới.'), '/admin/content/' . $id);
    }

    public function publish(string $id): void
    {
        ContentService::publish((int)$id, $this->int('version_id') ?: null, $this->str('note') ?: null);
        $this->back('Đã xuất bản.');
    }

    public function unpublish(string $id): void
    {
        ContentService::unpublish((int)$id, $this->str('reason', 'Gỡ bài'));
        $this->back('Đã gỡ khỏi website.');
    }

    public function reject(string $id): void
    {
        ContentService::reject((int)$id, $this->str('note', 'Chưa đạt'));
        $this->back('Đã trả bản nháp về.');
    }
}
