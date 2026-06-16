' Zatrzymuje serwer WWW oraz bota Discord (procesy z Oferty.vbs). Bez okna.
Option Explicit
Dim sh, cmd
Set sh = CreateObject("WScript.Shell")
' Zabija tylko procesy Pythona obslugujace server.py / discord_bot.py.
cmd = "powershell -NoProfile -WindowStyle Hidden -Command """ & _
  "Get-CimInstance Win32_Process -Filter \""Name='pythonw.exe' OR Name='python.exe'\"" | " & _
  "Where-Object { $_.CommandLine -like '*server.py*' -or $_.CommandLine -like '*discord_bot.py*' } | " & _
  "ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"""
sh.Run cmd, 0, True
