On Error Resume Next

Function CurrentPath()
    strPath = Wscript.ScriptFullName
    Set objFSO = CreateObject("Scripting.FileSystemObject")
    Set objFile = objFSO.GetFile(strPath)
    CurrentPath = objFSO.GetParentFolderName(objFile)
End Function

Function isConsole()
    Set objArgs = Wscript.Arguments
    isConsole = 0
    If objArgs.Count > 0 Then
        if objArgs(0) = "console" Then
            isConsole = 1
        End If
    End If
End Function

strCurrentPath = CurrentPath()

Dim oShell
Dim strArgs
Dim strExecutable
Dim python_cmd
Dim RunningLockFn
Dim quo

Set oShell = CreateObject("WScript.Shell")
oShell.CurrentDirectory = strCurrentPath

quo = """"

If isConsole() Then
    python_cmd = "python.exe"
Else
    python_cmd = "pythonw.exe"
End If

strExecutable = quo & strCurrentPath & "\python3\" & python_cmd & quo
strArgs = strExecutable & " " & quo & strCurrentPath & "\code\default\launcher\start.py" & quo
RunningLockFn = strCurrentPath & "\data\launcher\Running.Lck"

Set fso = CreateObject("Scripting.FileSystemObject")
oShell.Environment("Process")("PYTHONPATH") = ""
oShell.Environment("Process")("PYTHONHOME") = ""

Do
    StartTime = Timer
    oShell.Run strArgs, isConsole(), true
    EndTime = Timer
    run_cost = EndTime - StartTime
Loop Until (not fso.FileExists(RunningLockFn)) or run_cost < 20
