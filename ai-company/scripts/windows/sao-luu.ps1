# Sao lưu CSDL ra thư mục ai-company\backups (giữ 14 bản gần nhất).
# Chạy: powershell -ExecutionPolicy Bypass -File scripts\windows\sao-luu.ps1 [-ThuMucNgoai "E:\SaoLuuAI"]
# Nên đặt lịch hằng ngày trong Task Scheduler, và chỉ -ThuMucNgoai tới ổ ngoài hoặc thư mục OneDrive/Google Drive.
param([string]$ThuMucNgoai = "")
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $root
$dir = Join-Path $root "backups"
New-Item -ItemType Directory -Force -Path $dir | Out-Null
$file = Join-Path $dir ("aico-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".dump")
& docker compose exec -T db pg_dump -U aico -d aico -Fc -f /tmp/aico.dump
if ($LASTEXITCODE -ne 0) { Write-Host "Sao lưu thất bại: CSDL có đang chạy không? (docker compose ps)" -ForegroundColor Red; exit 1 }
& docker compose cp db:/tmp/aico.dump $file
& docker compose exec -T db rm -f /tmp/aico.dump
Write-Host ("Đã sao lưu: " + $file) -ForegroundColor Green
Get-ChildItem $dir -Filter "aico-*.dump" | Sort-Object Name -Descending | Select-Object -Skip 14 | Remove-Item
if ($ThuMucNgoai) {
    New-Item -ItemType Directory -Force -Path $ThuMucNgoai | Out-Null
    Copy-Item $file $ThuMucNgoai
    Write-Host ("Đã chép thêm ra: " + $ThuMucNgoai) -ForegroundColor Green
}
