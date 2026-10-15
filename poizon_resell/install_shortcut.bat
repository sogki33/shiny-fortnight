@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo [1/3] 파이썬 확인...
where pythonw >nul 2>nul
if errorlevel 1 (
  echo 파이썬이 없습니다. https://www.python.org/downloads/ 에서 설치하세요.
  echo 설치할 때 "Add python.exe to PATH" 를 꼭 체크하세요.
  pause
  exit /b 1
)
echo [2/3] 필요한 패키지 설치...
python -m pip install --quiet requests
echo [3/3] 바탕화면 바로가기 만들기...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$d=[Environment]::GetFolderPath('Desktop');" ^
  "$s=(New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $d '포이즌 리셀 스캐너.lnk'));" ^
  "$s.TargetPath=(Get-Command pythonw).Source;" ^
  "$s.Arguments='\"%~dp0app.py\"';" ^
  "$s.WorkingDirectory='%~dp0';" ^
  "$s.IconLocation='shell32.dll,22';" ^
  "$s.Save()"
echo.
echo 완료! 바탕화면의 "포이즌 리셀 스캐너" 아이콘을 더블클릭하세요.
pause
