<?php
declare(strict_types=1);

/**
 * Tác vụ định kỳ — đặt Cron Job trên hPanel mỗi 5 phút:
 *   /usr/bin/php /home/uXXX/domains/ten-mien/xuong/bin/cron.php
 * Gồm: hết hạn đơn chờ xác nhận, dọn sự kiện đồng bộ cũ, dọn khóa gửi lại/giới hạn tần suất.
 */
require __DIR__ . '/../app/bootstrap.php';

use App\Core\Audit;
use App\Core\Clock;
use App\Core\Db;
use App\Core\Settings;
use App\Domain\OrderService;
use App\Domain\SyncService;

$lock = fopen(sys_get_temp_dir() . '/xuong_cron.lock', 'c');
if (!flock($lock, LOCK_EX | LOCK_NB)) {
    exit(0); // lần chạy trước chưa xong
}

function run_job(string $name, callable $fn): void
{
    $start = Clock::nowDb();
    try {
        $detail = $fn();
        Db::insert('job_runs', ['job' => $name, 'status' => 'ok', 'detail' => json_enc($detail), 'started_at' => $start, 'finished_at' => Clock::nowDb()]);
        echo "[$name] ok " . json_enc($detail) . "\n";
    } catch (Throwable $e) {
        Db::insert('job_runs', ['job' => $name, 'status' => 'failed', 'detail' => mb_substr($e->getMessage(), 0, 1000), 'started_at' => $start, 'finished_at' => Clock::nowDb()]);
        Audit::error('cron', strtoupper($name) . '_FAILED', $e->getMessage());
        echo "[$name] LỖI " . $e->getMessage() . "\n";
    }
}

run_job('expire_orders', function () {
    $r = OrderService::expireDue();
    if ($r['failed'] > 0) {
        throw new RuntimeException('Có ' . $r['failed'] . ' đơn hết hạn xử lý lỗi: ' . json_enc($r));
    }
    return $r;
});

$minute = (int)Clock::now()->format('i');
if ($minute < 5) { // mỗi giờ một lần
    run_job('housekeeping', function () {
        $pruned = SyncService::prune();
        $idem = Db::exec('DELETE FROM idempotency_keys WHERE created_at < :c', ['c' => Clock::db(Clock::now()->modify('-7 days'))]);
        $rl = Db::exec('DELETE FROM rate_limits WHERE window_start < :c', ['c' => Clock::db(Clock::now()->modify('-1 day'))]);
        $days = Settings::int('chat_log_days', 90);
        $chat = Db::exec('DELETE FROM chat_questions WHERE created_at < :c', ['c' => Clock::db(Clock::now()->modify("-$days days"))]);
        return ['sync_events_pruned' => $pruned, 'idempotency_pruned' => $idem, 'rate_limits_pruned' => $rl, 'chat_pruned' => $chat];
    });
}
