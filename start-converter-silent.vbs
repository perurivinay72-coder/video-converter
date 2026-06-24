' Silent launcher for MarkItDown Auto-Converter (Whisper Edition)
' Runs the Python watcher script WITHOUT a terminal window.
' Drop this file in the video-converter folder and run it to start the watcher.

Dim pythonExe, scriptPath, workDir
pythonExe  = "C:\Users\Vinay Peruri\AppData\Local\Programs\Python\Python312\python.exe"
scriptPath = "C:\Users\Vinay Peruri\video-converter\auto converter.py"
workDir    = "C:\Users\Vinay Peruri\video-converter"

' Check if the watcher is already running – avoid duplicate processes
Dim objWMI, colProcesses, blnRunning
Set objWMI = GetObject("winmgmts:\\.\root\cimv2")
Set colProcesses = objWMI.ExecQuery("SELECT * FROM Win32_Process WHERE Name='python.exe'")
blnRunning = False
For Each proc In colProcesses
    If InStr(proc.CommandLine, "auto converter.py") > 0 Then
        blnRunning = True
    End If
Next
Set colProcesses = Nothing
Set objWMI = Nothing

If blnRunning Then
    ' Already running – do nothing
    WScript.Quit 0
End If

' Launch in watch mode (NO --once flag) and hide the window
Dim shell
Set shell = CreateObject("WScript.Shell")
shell.CurrentDirectory = workDir
' Window style 0 = hidden, bWaitOnReturn = False (non-blocking)
shell.Run """" & pythonExe & """ """ & scriptPath & """", 0, False
Set shell = Nothing
