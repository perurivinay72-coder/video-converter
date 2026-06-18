' Silent launcher for MarkItDown Auto-Converter
' Runs the Python script without showing any terminal window

Dim pythonExe, scriptPath, workDir
pythonExe = "C:\Users\Vinay Peruri\AppData\Local\Programs\Python\Python312\python.exe"
scriptPath = "C:\Users\Vinay Peruri\video-converter\auto converter.py"
workDir    = "C:\Users\Vinay Peruri\video-converter"

Dim shell
Set shell = CreateObject("WScript.Shell")
shell.CurrentDirectory = workDir
shell.Run """" & pythonExe & """ """ & scriptPath & """", 0, False
Set shell = Nothing
