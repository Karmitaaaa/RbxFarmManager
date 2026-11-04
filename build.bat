@echo off
REM Empaqueta RbxFarm Manager en ..\Build\RbxFarmManager\RbxFarmManager.exe
REM (la carpeta Build queda al lado de la carpeta del proyecto)
setlocal
cd /d "%~dp0"
for %%I in ("%~dp0..\Build") do set "BUILD_DIR=%%~fI"
set "TEMP_DIR=%TEMP%\RbxFarmManager-build"

if not exist .venv (
    py -3 -m venv .venv || goto :error
)
call .venv\Scripts\activate.bat || goto :error
python -m pip install --upgrade pip
python -m pip install -r requirements.txt || goto :error
python tools\make_icon.py || goto :error

pyinstaller --noconfirm --clean --windowed ^
  --name RbxFarmManager ^
  --icon "%~dp0assets\icon.ico" ^
  --collect-submodules pynput ^
  --hidden-import win32timezone ^
  --add-data "%~dp0VERSION;." ^
  --add-data "%~dp0locales;locales" ^
  --distpath "%BUILD_DIR%" ^
  --workpath "%TEMP_DIR%\work" ^
  --specpath "%TEMP_DIR%" ^
  "%~dp0main.py" || goto :error

REM Recorte: herramientas de desarrollador del navegador integrado e idiomas que no se usan (~125 MB)
set "QT_DIR=%BUILD_DIR%\RbxFarmManager\_internal\PySide6"
del /q "%QT_DIR%\resources\qtwebengine_devtools_resources*.pak" 2>nul
for %%F in ("%QT_DIR%\translations\qtwebengine_locales\*.pak") do (
    if /I not "%%~nF"=="es" if /I not "%%~nF"=="es-419" if /I not "%%~nF"=="en-US" del /q "%%F"
)

echo.
echo Listo: %BUILD_DIR%\RbxFarmManager\RbxFarmManager.exe

REM Instalador (solo si Inno Setup 6 esta instalado)
set /p APP_VERSION=<VERSION
set "ISCC="
for %%P in ("%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" "%ProgramFiles%\Inno Setup 6\ISCC.exe" ^
            "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe") do if exist %%P set "ISCC=%%~P"
if not defined ISCC (
    echo Inno Setup 6 no esta instalado: se omite el instalador.
    exit /b 0
)
"%ISCC%" /Q /DAppVersion=%APP_VERSION% "/DBuildDir=%BUILD_DIR%" installer\RbxFarmManager.iss || goto :error
"%ISCC%" /Q "/DBuildDir=%BUILD_DIR%" installer\RbxFarmManager-WebSetup.iss || goto :error
echo Instalador completo: %BUILD_DIR%\Instalador\RbxFarmManager-Setup.exe  (version %APP_VERSION%)
echo Instalador web:      %BUILD_DIR%\Instalador\RbxFarmManager-WebSetup.exe
exit /b 0

:error
echo.
echo La compilacion fallo. Revisa los mensajes de arriba.
exit /b 1
