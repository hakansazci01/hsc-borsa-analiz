# ============================================================
# TEK BAŞLATMA NOKTASI KURULUMU — YÖNETİCİ OLARAK ÇALIŞTIR
# Kullanım (Yönetici cmd):
# powershell -ExecutionPolicy Bypass -File "C:\Users\hakan\OneDrive\Desktop\al sat boto\setup_autostart.ps1"
# ============================================================
$ErrorActionPreference = 'Stop'

$root     = 'C:\Users\hakan\OneDrive\Desktop\al sat boto'
$py       = Join-Path $root '.venv\Scripts\python.exe'
$launcher = Join-Path $root 'launch_all.py'
$log      = Join-Path $root 'users\autostart.log'

function Log([string]$m) {
    $line = "[$([datetime]::Now.ToString('yyyy-MM-dd HH:mm:ss'))] $m"
    New-Item -ItemType Directory -Path (Split-Path $log) -Force | Out-Null
    Add-Content -Path $log -Value $line
    Write-Host $line
}

if (-not (Test-Path $py))       { Log "BAŞARISIZ — python yok: $py"; exit 1 }
if (-not (Test-Path $launcher)) { Log "BAŞARISIZ — launcher yok: $launcher"; exit 1 }

# 1) Diğer iki başlatma noktasını KALDIR (tek nokta kalsın)
Remove-ItemProperty -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run' -Name 'HSC_Bot' -ErrorAction SilentlyContinue
Remove-Item (Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\Startup\HSC_Bot_Start.bat') -Force -ErrorAction SilentlyContinue
Log "Startup bat ve Registry Run key kaldırıldı"

# 2) Görevi sıfırdan kur — boşluklu OneDrive yolu tırnakla korunuyor
Unregister-ScheduledTask -TaskName 'HSC_Bot_Launcher' -Confirm:$false -ErrorAction SilentlyContinue

$action   = New-ScheduledTaskAction -Execute $py -Argument ('"' + $launcher + '"') -WorkingDirectory $root
$trigger  = New-ScheduledTaskTrigger -AtLogOn
$trigger.Delay = 'PT30S'
$principal = New-ScheduledTaskPrincipal -UserId 'hakan' -LogonType Interactive -RunLevel Highest
$settings  = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 72)

Register-ScheduledTask -TaskName 'HSC_Bot_Launcher' -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
Log "Görev kuruldu: ONLOGON + 30 sn gecikme + YÖNETİCİ — BAŞARILI"

# 3) Kanıt
$t = Get-ScheduledTask -TaskName 'HSC_Bot_Launcher'
Log "Doğrulama: STATE=$($t.State) TRIGGER=$($t.Triggers[0].CimClass.CimClassName) DELAY=$($t.Triggers[0].Delay) RUNLEVEL=$($t.Principal.RunLevel)"
Log "KOMUT: $($t.Actions[0].Execute) $($t.Actions[0].Arguments)"
