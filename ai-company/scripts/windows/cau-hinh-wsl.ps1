# Giới hạn WSL2 (nơi Docker chạy) dùng tối đa 6 GB RAM + 4 GB swap, để Windows còn ~10 GB cho việc khác.
# Sao lưu .wslconfig cũ (nếu có) trước khi ghi. Chạy: powershell -ExecutionPolicy Bypass -File scripts\windows\cau-hinh-wsl.ps1
$ErrorActionPreference = "Stop"
$cfg = Join-Path $env:USERPROFILE ".wslconfig"
if (Test-Path $cfg) {
    $bak = $cfg + "." + (Get-Date -Format "yyyyMMdd-HHmmss") + ".bak"
    Copy-Item $cfg $bak
    Write-Host ("Đã sao lưu cấu hình cũ: " + $bak)
}
$noiDung = @"
[wsl2]
memory=6GB
swap=4GB
processors=4
"@
Set-Content -Path $cfg -Value $noiDung -Encoding ASCII
Write-Host ("Đã ghi " + $cfg) -ForegroundColor Green
Write-Host "Để áp dụng: thoát Docker Desktop, chạy  wsl --shutdown , rồi mở lại Docker Desktop."
