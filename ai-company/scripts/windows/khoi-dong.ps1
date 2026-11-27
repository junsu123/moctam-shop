# Khởi động AI Marketing Company và mở trang quản trị. Chạy: powershell -ExecutionPolicy Bypass -File scripts\windows\khoi-dong.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $root
if (-not (Test-Path ".env")) { Write-Host "Chưa có .env: chạy scripts\windows\tao-env.ps1 trước." -ForegroundColor Red; exit 1 }

Write-Host "Đang dựng và khởi động (lần đầu mất vài phút để tải và build)..."
& docker compose up -d --build
if ($LASTEXITCODE -ne 0) { Write-Host "docker compose báo lỗi. Xem chi tiết:  docker compose logs --tail 50" -ForegroundColor Red; exit 1 }

$url = "http://127.0.0.1:3000"
for ($i = 0; $i -lt 60; $i++) {
    try {
        $r = Invoke-WebRequest -Uri ($url + "/api/v1/health/ready") -UseBasicParsing -TimeoutSec 3
        if ($r.StatusCode -eq 200) { break }
    } catch { }
    Start-Sleep -Seconds 3
}
try {
    $r = Invoke-WebRequest -Uri ($url + "/api/v1/health/ready") -UseBasicParsing -TimeoutSec 3
    Write-Host "Hệ thống đã sẵn sàng." -ForegroundColor Green
} catch {
    Write-Host "Hệ thống chưa sẵn sàng sau 3 phút. Trang quản trị vẫn mở để xem mục nào chưa chạy." -ForegroundColor Yellow
}
# Lần đầu (chưa có tài khoản Owner): in mã thiết lập dùng một lần và mở thẳng trang thiết lập
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$setup = & docker compose exec -T backend python -m app.cli setup-token 2>$null
if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host ($setup -join "`r`n") -ForegroundColor Cyan
    Write-Host "Giữ cửa sổ này mở trong lúc thiết lập." -ForegroundColor Cyan
    Start-Process ($url + "/thiet-lap")
} else {
    Start-Process $url
}
