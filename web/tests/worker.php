<?php
declare(strict_types=1);

/** Tiến trình con cho ca kiểm thử đồng thời. */
require __DIR__ . '/lib.php';

use App\Core\ApiError;
use App\Core\Db;
use App\Domain\OrderService;
use App\Domain\SyncService;

$job = json_decode(base64_decode($argv[1]), true);
while (microtime(true) < $job['start_at']) {
    usleep(500);
}
try {
    switch ($job['action']) {
        case 'create_order':
            $r = OrderService::create($job['input'], $job['session'], $job['key']);
            echo json_enc(['ok' => true, 'code' => $r['order']['code'], 'replayed' => $r['replayed'], 'discount' => $r['order']['voucher_discount']]);
            break;
        case 'emit_slow':
            // Giao dịch lấy seq rồi giữ khóa một lúc trước khi commit
            $res = Db::tx(function () use ($job) {
                usleep((int)$job['delay_before'] * 1000);
                $seq = SyncService::emit('test', (int)$job['entity'], 'test.event', ['who' => $job['who']]);
                usleep((int)$job['hold_ms'] * 1000);
                return $seq;
            });
            echo json_enc(['ok' => true, 'seq' => $res, 'committed_at' => microtime(true)]);
            break;
    }
} catch (ApiError $e) {
    echo json_enc(['ok' => false, 'error' => $e->errorCode, 'details' => $e->data]);
} catch (Throwable $e) {
    echo json_enc(['ok' => false, 'error' => 'EXCEPTION', 'message' => $e->getMessage()]);
}
