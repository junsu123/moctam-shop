<?php
declare(strict_types=1);

namespace App\Http\Admin;

use App\Core\Router;

final class Routes
{
    public static function register(Router $r): void
    {
        $r->get('/admin/login', [AuthController::class, 'loginForm']);
        $r->post('/admin/login', [AuthController::class, 'login']);
        $r->post('/admin/logout', [AuthController::class, 'logout']);
        $r->get('/admin', [DashboardController::class, 'index']);
        $r->get('/admin/monitor', [DashboardController::class, 'monitor']);

        // Đơn hàng
        $r->get('/admin/orders', [OrderController::class, 'index']);
        $r->get('/admin/orders/{id}', [OrderController::class, 'show']);
        $r->post('/admin/orders/{id}/transition', [OrderController::class, 'transition']);
        $r->post('/admin/orders/{id}/tracking', [OrderController::class, 'tracking']);
        $r->post('/admin/orders/{id}/cod', [OrderController::class, 'cod']);
        $r->post('/admin/orders/{id}/refund', [OrderController::class, 'refund']);

        // Kho
        $r->get('/admin/inventory', [InventoryController::class, 'index']);
        $r->post('/admin/inventory/{sku}/adjust', [InventoryController::class, 'adjust']);
        $r->get('/admin/inventory/movements', [InventoryController::class, 'movements']);

        // Sản phẩm
        $r->get('/admin/products', [CatalogController::class, 'index']);
        $r->get('/admin/products/new', [CatalogController::class, 'create']);
        $r->get('/admin/products/{id}', [CatalogController::class, 'edit']);
        $r->post('/admin/products/save', [CatalogController::class, 'save']);
        $r->post('/admin/products/{id}/sku', [CatalogController::class, 'sku']);
        $r->post('/admin/products/{id}/image', [CatalogController::class, 'image']);
        $r->post('/admin/products/{id}/image-delete', [CatalogController::class, 'imageDelete']);
        $r->post('/admin/products/{id}/relation', [CatalogController::class, 'relation']);
        $r->post('/admin/products/{id}/delete', [CatalogController::class, 'delete']);
        $r->get('/admin/categories', [CatalogController::class, 'categories']);
        $r->post('/admin/categories/save', [CatalogController::class, 'saveCategory']);
        $r->get('/admin/crosssell', [CatalogController::class, 'crosssell']);
        $r->post('/admin/crosssell/{id}/review', [CatalogController::class, 'reviewCrosssell']);

        // Vùng giao, ưu đãi
        $r->get('/admin/shipping', [PromoController::class, 'shipping']);
        $r->post('/admin/shipping/zone', [PromoController::class, 'saveZone']);
        $r->post('/admin/shipping/rate', [PromoController::class, 'addRate']);
        $r->get('/admin/vouchers', [PromoController::class, 'vouchers']);
        $r->get('/admin/vouchers/{id}', [PromoController::class, 'voucherForm']);
        $r->post('/admin/vouchers/save', [PromoController::class, 'saveVoucher']);
        $r->get('/admin/flash-sales', [PromoController::class, 'flashSales']);
        $r->get('/admin/flash-sales/{id}', [PromoController::class, 'flashForm']);
        $r->post('/admin/flash-sales/save', [PromoController::class, 'saveFlash']);

        // Thanh toán
        $r->get('/admin/payments', [PaymentController::class, 'index']);
        $r->post('/admin/payments/vietqr', [PaymentController::class, 'recordVietQr']);
        $r->get('/admin/discrepancies', [PaymentController::class, 'discrepancies']);
        $r->post('/admin/discrepancies/{id}/resolve', [PaymentController::class, 'resolve']);
        $r->get('/admin/refunds', [PaymentController::class, 'refunds']);
        $r->post('/admin/refunds/{id}/complete', [PaymentController::class, 'complete']);
        $r->post('/admin/refunds/{id}/cancel', [PaymentController::class, 'cancel']);

        // Nội dung
        $r->get('/admin/content', [ContentController::class, 'index']);
        $r->get('/admin/content/new', [ContentController::class, 'create']);
        $r->get('/admin/content/{id}', [ContentController::class, 'edit']);
        $r->post('/admin/content/save', [ContentController::class, 'save']);
        $r->post('/admin/content/{id}/publish', [ContentController::class, 'publish']);
        $r->post('/admin/content/{id}/unpublish', [ContentController::class, 'unpublish']);
        $r->post('/admin/content/{id}/reject', [ContentController::class, 'reject']);

        // Chăm sóc lại
        $r->get('/admin/care', [CareController::class, 'index']);
        $r->post('/admin/care/{id}/status', [CareController::class, 'status']);
        $r->get('/admin/care/export', [CareController::class, 'export']);

        // Tài khoản đăng nhập của khách (Google / Facebook)
        $r->get('/admin/customer-accounts', [CustomerAccountController::class, 'index']);
        $r->get('/admin/customer-accounts/{id}', [CustomerAccountController::class, 'show']);
        $r->post('/admin/customer-accounts/{id}/lock', [CustomerAccountController::class, 'lock']);
        $r->post('/admin/customer-accounts/{id}/unlock', [CustomerAccountController::class, 'unlock']);
        $r->post('/admin/customer-accounts/{id}/logout', [CustomerAccountController::class, 'logout']);
        $r->post('/admin/customer-accounts/{id}/unlink', [CustomerAccountController::class, 'unlink']);
        $r->post('/admin/customer-accounts/{id}/delete', [CustomerAccountController::class, 'delete']);

        // Hệ thống
        $r->get('/admin/users', [SystemController::class, 'users']);
        $r->post('/admin/users/save', [SystemController::class, 'saveUser']);
        $r->post('/admin/users/{id}/unlock', [SystemController::class, 'unlockUser']);
        $r->get('/admin/roles', [SystemController::class, 'roles']);
        $r->post('/admin/roles/save', [SystemController::class, 'saveRole']);
        $r->get('/admin/settings', [SystemController::class, 'settings']);
        $r->post('/admin/settings', [SystemController::class, 'saveSettings']);
        $r->get('/admin/api-keys', [SystemController::class, 'apiKeys']);
        $r->post('/admin/api-keys/create', [SystemController::class, 'createKey']);
        $r->post('/admin/api-keys/{id}/revoke', [SystemController::class, 'revokeKey']);
        $r->get('/admin/audit', [SystemController::class, 'audit']);
        $r->get('/admin/system/reset', [ResetController::class, 'form']);
        $r->post('/admin/system/reset', [ResetController::class, 'run']);
        $r->get('/admin/account', [SystemController::class, 'account']);
        $r->post('/admin/account/password', [SystemController::class, 'changePassword']);
    }
}
