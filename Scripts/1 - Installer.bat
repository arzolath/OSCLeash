@echo off
pushd "%~dp0.."
python setup.py bdist_msi
set "BUILD_RESULT=%ERRORLEVEL%"
popd
pause
exit /b %BUILD_RESULT%
