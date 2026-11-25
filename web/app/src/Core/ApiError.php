<?php
declare(strict_types=1);

namespace App\Core;

use RuntimeException;

/**
 * Lỗi nghiệp vụ có mã ổn định (đặc tả §5.3).
 * Mã: VALIDATION_ERROR, QUOTE_CHANGED, OUT_OF_STOCK, VOUCHER_INVALID, ZONE_NOT_SERVED,
 * IDEMPOTENCY_CONFLICT, INVALID_TRANSITION, FORBIDDEN, NOT_FOUND, RATE_LIMITED, ...
 */
final class ApiError extends RuntimeException
{
    public function __construct(
        public readonly string $errorCode,
        string $message,
        public readonly int $status = 400,
        public readonly array $data = [],
    ) {
        parent::__construct($message);
    }

    public function toArray(): array
    {
        return ['error' => ['code' => $this->errorCode, 'message' => $this->getMessage()] + ($this->data ? ['details' => $this->data] : [])];
    }

    public static function validation(array $fields, string $message = 'Thông tin chưa hợp lệ, vui lòng kiểm tra các trường được đánh dấu.'): self
    {
        return new self('VALIDATION_ERROR', $message, 422, ['fields' => $fields]);
    }

    public static function forbidden(string $message = 'Bạn không có quyền thực hiện thao tác này.'): self
    {
        return new self('FORBIDDEN', $message, 403);
    }

    public static function notFound(string $message = 'Không tìm thấy dữ liệu.'): self
    {
        return new self('NOT_FOUND', $message, 404);
    }
}
