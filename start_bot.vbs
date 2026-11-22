' HSC Bot — Masaüstünden başlatma (çift tık = tek işlem)
' Siyah konsol penceresi açmaz; Streamlit paneli tarayıcıda açılır.
Option Explicit

Dim root, py, launcher, logPath, fso, ts, shell
Dim objWMIService, colProcs, objProc, killCount

root = "C:\Users\hakan\OneDrive\Desktop\al sat boto"
py = root & "\.venv\Scripts\python.exe"
launcher = root & "\launch_all.py"
logPath = root & "\users\manual_start.log"

Set fso = CreateObject("Scripting.FileSystemObject")
If Not fso.FolderExists(root & "\users") Then fso.CreateFolder root & "\users"

' 1) Eski watchdog / motor / scheduler kopyalarını kapat
killCount = 0
Set objWMIService = GetObject("winmgmts:\\.\root\cimv2")
Set colProcs = objWMIService.ExecQuery("SELECT ProcessId, CommandLine FROM Win32_Process WHERE Name = 'python.exe'")
For Each objProc In colProcs
    If Not IsNull(objProc.CommandLine) Then
        If InStr(objProc.CommandLine, "ui.watchdog_runner") > 0 Or _
           InStr(objProc.CommandLine, "ui.tr_runner") > 0 Or _
           InStr(objProc.CommandLine, "ui.autonomous_scheduler") > 0 Then
            On Error Resume Next
            objProc.Terminate()
            If Err.Number = 0 Then killCount = killCount + 1
            On Error GoTo 0
        End If
    End If
Next

' 2) Eski kilit dosyalarını sıfırla (yabancı PID / wslhost.exe sorunu)
If fso.FileExists(root & "\users\TR_SCALPER_LOCK") Then fso.DeleteFile root & "\users\TR_SCALPER_LOCK", True
If fso.FileExists(root & "\users\WATCHDOG_SINGLE.lock") Then fso.DeleteFile root & "\users\WATCHDOG_SINGLE.lock", True

' 3) Başlatma kaydı
Set ts = fso.OpenTextFile(logPath, 8, True)
ts.WriteLine "[" & Now & "] Masaüstünden başlatıldı — eski kopyalar temizlendi: " & killCount & " — kilit sıfırlandı"
ts.Close

' 4) launch_all.py'yi gizli pencerede çalıştır (sonuç manual_start.log'a yazılır)
Set shell = CreateObject("WScript.Shell")
shell.Environment("PROCESS")("HSC_START_LOG") = "manual_start.log"
shell.Environment("PROCESS")("HSC_START_SOURCE") = "masaustu"
shell.CurrentDirectory = root
shell.Run """" & py & """ """ & launcher & """", 0, False
