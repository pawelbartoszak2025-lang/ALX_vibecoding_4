' Uruchamia BEZ zadnego okna konsoli:
'   1) lokalny serwer WWW (strona + przycisk pobierania/wysylki),
'   2) bota Discord ze slash-komendami (/poznan, /krakow, /warszawa, /gdansk).
' Nastepnie otwiera strone w przegladarce. Wystarczy dwuklik tego pliku.
Option Explicit
Dim sh, fso, here
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
here = fso.GetParentFolderName(WScript.ScriptFullName)
sh.CurrentDirectory = here

Sub StartHidden(scriptName)
    ' pythonw.exe = Python bez okna konsoli. 0 = ukryte, False = nie czekaj.
    On Error Resume Next
    sh.Run "pythonw """ & here & "\" & scriptName & """", 0, False
    If Err.Number <> 0 Then
        Err.Clear
        sh.Run "python """ & here & "\" & scriptName & """", 0, False
    End If
    On Error Goto 0
End Sub

StartHidden "server.py"
StartHidden "discord_bot.py"
