# Tạo tệp ai-company\.env với mật khẩu CSDL và khóa chủ ngẫu nhiên. KHÔNG ghi đè nếu .env đã có.
# Chạy từ thư mục ai-company: powershell -ExecutionPolicy Bypass -File scripts\windows\tao-env.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$tepEnv = Join-Path $root ".env"
if (Test-Path $tepEnv) { Write-Host ("Đã có " + $tepEnv + ": giữ nguyên, không ghi đè.") -ForegroundColor Yellow; exit 0 }

function NgauNhien([int]$soByte) {
    $b = New-Object byte[] $soByte
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $rng.GetBytes($b)
    $rng.Dispose()
    return ([System.BitConverter]::ToString($b) -replace "-", "").ToLower()
}
$noiDung = @(
    "# Tạo tự động lúc " + (Get-Date -Format "yyyy-MM-dd HH:mm") + ". Giữ bí mật; không đưa lên git.",
    "AICO_DB_PASSWORD=" + (NgauNhien 24),
    "AICO_MASTER_KEY=" + (NgauNhien 32)
)
[System.IO.File]::WriteAllLines($tepEnv, $noiDung, (New-Object System.Text.UTF8Encoding($false)))
Write-Host ("Đã tạo " + $tepEnv) -ForegroundColor Green
Write-Host "Hãy chép tệp này vào nơi an toàn (vd USB riêng): mất AICO_MASTER_KEY thì phải nhập lại các secret trong trang quản trị."
