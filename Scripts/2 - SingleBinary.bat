@echo off
pushd "%~dp0.."
python -m PyInstaller --noconfirm --onefile --console --icon Resources\VRChatOSCLeash.ico --workpath Scripts\build --distpath Scripts\dist --specpath Scripts OSCLeash.py
set "BUILD_RESULT=%ERRORLEVEL%"
popd
pause
exit /b %BUILD_RESULT%
