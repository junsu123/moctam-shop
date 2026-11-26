# Kiểm tra máy Windows có đủ điều kiện chạy AI Marketing Company không. Chỉ ĐỌC, không thay đổi gì.
# Chạy: powershell -ExecutionPolicy Bypass -File scripts\windows\kiem-tra-may.ps1
$ErrorActionPreference = "Continue"
$ok = $true
function Dat($ten, $chitiet) { Write-Host ("[ĐẠT]   " + $ten + ": " + $chitiet) -ForegroundColor Green }
function Truot($ten, $chitiet) { Write-Host ("[CHƯA]  " + $ten + ": " + $chitiet) -ForegroundColor Red; $script:ok = $false }
function Luuy($ten, $chitiet) { Write-Host ("[LƯU Ý] " + $ten + ": " + $chitiet) -ForegroundColor Yellow }

$os = Get-CimInstance Win32_OperatingSystem
if ([int]$os.BuildNumber -ge 22000) { Dat "Windows" $os.Caption } else { Truot "Windows" ("Cần Windows 11, máy đang là " + $os.Caption) }

$ramGB = [math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB)
if ($ramGB -ge 32) { Dat "RAM" ("$ramGB GB") }
elseif ($ramGB -ge 16) { Luuy "RAM" ("$ramGB GB: đủ chạy (hệ thống dùng tối đa 6 GB). Nâng lên 32 GB khi mở rộng trên 15 agent.") }
else { Truot "RAM" ("$ramGB GB: cần tối thiểu 16 GB") }

$cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
if ($cpu.VirtualizationFirmwareEnabled) { Dat "Ảo hóa (VT-x)" "đã bật trong BIOS" }
else { Luuy "Ảo hóa (VT-x)" "Windows không báo được hoặc chưa bật. Nếu Docker báo lỗi WSL2, hãy bật Intel VT-x trong BIOS." }

$drive = Get-PSDrive -Name ($env:SystemDrive.TrimEnd(':'))
$freeGB = [math]::Round($drive.Free / 1GB)
if ($freeGB -ge 100) { Dat "Ổ đĩa trống" ("$freeGB GB trên " + $env:SystemDrive) } else { Luuy "Ổ đĩa trống" ("$freeGB GB trên " + $env:SystemDrive + ": nên còn ít nhất 100 GB") }

$wsl = Get-Command wsl.exe -ErrorAction SilentlyContinue
if ($wsl) {
    $st = (& wsl.exe --status 2>&1 | Out-String)
    if ($LASTEXITCODE -eq 0) { Dat "WSL2" "đã cài" } else { Truot "WSL2" "chưa cài: mở PowerShell (Admin) chạy  wsl --install  rồi khởi động lại máy" }
} else { Truot "WSL2" "chưa cài: mở PowerShell (Admin) chạy  wsl --install  rồi khởi động lại máy" }

$docker = Get-Command docker -ErrorAction SilentlyContinue
if ($docker) {
    $v = (& docker version --format "{{.Server.Version}}" 2>$null)
    if ($LASTEXITCODE -eq 0 -and $v) { Dat "Docker Desktop" ("đang chạy, phiên bản " + $v) }
    else { Truot "Docker Desktop" "đã cài nhưng chưa chạy: mở Docker Desktop và đợi biểu tượng cá voi chuyển xanh" }
} else { Truot "Docker Desktop" "chưa cài: tải tại https://www.docker.com/products/docker-desktop/" }

$cfg = Join-Path $env:USERPROFILE ".wslconfig"
if ((Test-Path $cfg) -and ((Get-Content $cfg -Raw) -match "memory\s*=\s*6GB")) { Dat ".wslconfig" "giới hạn RAM 6 GB" }
else { Luuy ".wslconfig" "chưa giới hạn RAM cho WSL2: chạy scripts\windows\cau-hinh-wsl.ps1" }

Write-Host ""
if ($ok) { Write-Host "Máy đã sẵn sàng. Bước tiếp: scripts\windows\tao-env.ps1 rồi scripts\windows\khoi-dong.ps1" -ForegroundColor Green }
else { Write-Host "Còn mục CHƯA đạt ở trên. Làm theo hướng dẫn từng mục rồi chạy lại script này." -ForegroundColor Red; exit 1 }
