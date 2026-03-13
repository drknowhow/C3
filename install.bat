@echo off
setlocal EnableDelayedExpansion

:: ─── Get C3 Version ────────────────────────────────────────────────────────
set "C3_HOME=%~dp0"
if "%C3_HOME:~-1%"=="\" set "C3_HOME=%C3_HOME:~0,-1%"

for /f "tokens=2 delims==" %%v in ('findstr "__version__ =" "%C3_HOME%\cli\c3.py"') do (
    set "RAW_VER=%%v"
    set "C3_VER=!RAW_VER:"=!"
    set "C3_VER=!C3_VER: =!"
)

echo.
echo   ============================================================
echo     C3 - Claude Code Companion  v!C3_VER!
echo     Windows Installer
echo   ============================================================
echo.

:: ─── Check Python ──────────────────────────────────────────────────────────
where python >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo   [ERROR] Python not found.
    echo   Install Python from https://python.org
    echo   Check "Add Python to PATH" during install.
    echo.
    pause
    exit /b 1
)

for /f "tokens=*" %%v in ('python --version 2^>^&1') do set "PY_VER=%%v"
echo   Python : %PY_VER%
echo   C3 Home: %C3_HOME%
echo.

:: ─── [1/5] Python dependencies ─────────────────────────────────────────────
echo   [1/5] Installing Python dependencies...
python -m pip install -r "%C3_HOME%\requirements.txt" textual -q 2>nul
if %ERRORLEVEL% neq 0 (
    echo         Retrying with --user flag...
    python -m pip install -r "%C3_HOME%\requirements.txt" textual --user -q 2>nul
)
echo         Done.
echo.

:: ─── [2/5] Create c3 command ────────────────────────────────────────────────
echo   [2/5] Creating c3 command...

for /f "tokens=*" %%p in ('python -c "import sys; print(sys.prefix)" 2^>^&1') do set "PYTHON_DIR=%%p"
set "SCRIPTS_DIR=%PYTHON_DIR%\Scripts"

if exist "%SCRIPTS_DIR%" (
    set "WRAPPER=%SCRIPTS_DIR%\c3.bat"
) else (
    set "WRAPPER=%USERPROFILE%\.local\bin\c3.bat"
    if not exist "%USERPROFILE%\.local\bin" mkdir "%USERPROFILE%\.local\bin"
)

:: System-wide wrapper (on PATH)
(
    echo @echo off
    echo set "C3_HOME=%C3_HOME%"
    echo set "PYTHONPATH=%%C3_HOME%%"
    echo if "%%~1"=="" ^(
    echo     python "%%C3_HOME%%\tui\main.py"
    echo ^) else ^(
    echo     python "%%C3_HOME%%\cli\c3.py" %%*
    echo ^)
) > "!WRAPPER!"
echo         Installed : !WRAPPER!

:: Local backup in project root
(
    echo @echo off
    echo set "C3_WRAPPER_HOME=%%~dp0"
    echo set "PYTHONPATH=%%C3_WRAPPER_HOME%%"
    echo if "%%~1"=="" ^(
    echo     python "%%C3_WRAPPER_HOME%%tui\main.py"
    echo ^) else ^(
    echo     python "%%C3_WRAPPER_HOME%%\cli\c3.py" %%*
    echo ^)
) > "%C3_HOME%\c3.bat"
echo         Backup    : %C3_HOME%\c3.bat
echo.

:: ─── [3/5] Initialize global ~/.c3 directory ───────────────────────────────
echo   [3/5] Initializing global C3 data directory...

set "C3_DATA=%USERPROFILE%\.c3"
if not exist "%C3_DATA%" (
    mkdir "%C3_DATA%"
    echo         Created : %C3_DATA%
) else (
    echo         Exists  : %C3_DATA%
)

:: Write default hub_config.json if not present
set "HUB_CFG=%C3_DATA%\hub_config.json"
if not exist "%HUB_CFG%" (
    (
        echo {
        echo   "port": 3330,
        echo   "auto_open_browser": true
        echo }
    ) > "%HUB_CFG%"
    echo         Created : %HUB_CFG%
) else (
    echo         Exists  : %HUB_CFG%
)

:: Write empty projects.json if not present
set "PROJ_FILE=%C3_DATA%\projects.json"
if not exist "%PROJ_FILE%" (
    (
        echo {"projects": []}
    ) > "%PROJ_FILE%"
    echo         Created : %PROJ_FILE%
) else (
    echo         Exists  : %PROJ_FILE%
)

echo.

:: ─── [4/5] Check pythonw.exe for background hub service ────────────────────
echo   [4/5] Checking background service prerequisites...

for /f "tokens=*" %%p in ('python -c "import sys,os; print(os.path.join(os.path.dirname(sys.executable),'pythonw.exe'))" 2^>^&1') do set "PYTHONW=%%p"

if exist "!PYTHONW!" (
    echo         pythonw.exe : OK  ^(background hub service supported^)
) else (
    echo         [WARN] pythonw.exe not found at: !PYTHONW!
    echo               The hub can still run, but "Install Service" may open a console window.
    echo               Full Python installer from python.org includes pythonw.exe.
)
echo.

:: ─── [5/5] Verify installation ─────────────────────────────────────────────
echo   [5/5] Verifying installation...
set "PYTHONPATH=%C3_HOME%"

:: CLI
python "%C3_HOME%\cli\c3.py" --help >nul 2>&1
if %ERRORLEVEL% equ 0 (
    echo         CLI (c3)         : OK
) else (
    echo         [WARN] CLI verification failed — check Python path.
)

:: TUI (Textual)
python -c "import textual" >nul 2>&1
if %ERRORLEVEL% equ 0 (
    echo         TUI (Textual)    : OK
) else (
    echo         [WARN] Textual not found — run: pip install textual
)

:: Flask (web UI + hub)
python -c "import flask" >nul 2>&1
if %ERRORLEVEL% equ 0 (
    echo         Web UI (Flask)   : OK
) else (
    echo         [WARN] Flask not found — run: pip install flask
)

:: Hub server
python -c "import sys; sys.path.insert(0,'%C3_HOME%'); from cli.hub_server import C3_VERSION" >nul 2>&1
if %ERRORLEVEL% equ 0 (
    echo         Project Hub      : OK
) else (
    echo         [WARN] Project Hub (hub_server) failed to import.
)

:: Project manager
python -c "import sys; sys.path.insert(0,'%C3_HOME%'); from services.project_manager import ProjectManager" >nul 2>&1
if %ERRORLEVEL% equ 0 (
    echo         Project Manager  : OK
) else (
    echo         [WARN] ProjectManager failed to import.
)

:: Hub service
python -c "import sys; sys.path.insert(0,'%C3_HOME%'); from services.hub_service import HubService" >nul 2>&1
if %ERRORLEVEL% equ 0 (
    echo         Hub Service Mgr  : OK
) else (
    echo         [WARN] HubService failed to import.
)

:: MCP server
python -c "import sys; sys.path.insert(0,'%C3_HOME%'); import fastmcp" >nul 2>&1
if %ERRORLEVEL% equ 0 (
    echo         MCP (FastMCP)    : OK
) else (
    echo         [WARN] FastMCP not found — run: pip install fastmcp
)

echo.
echo   ============================================================
echo     Installation complete!
echo   ============================================================
echo.
echo   COMMANDS
echo   --------
echo     c3                    Open interactive TUI  (Projects hub by default)
echo     c3 hub                Launch Project Hub web UI  (port 3330)
echo     c3 hub --no-browser   Start hub in background without opening browser
echo     c3 init .             Initialize C3 for current project
echo     c3 ui                 Launch per-project web dashboard
echo     c3 projects list      List all registered projects (CLI)
echo     c3 projects add .     Register current directory as a project
echo.
echo   BACKGROUND SERVICE
echo   ------------------
echo     From the Project Hub (c3 hub), open Settings ^> Install Service
echo     to register the hub as a Windows startup task that runs
echo     automatically on login — no terminal needed.
echo.
echo     Hub config : %HUB_CFG%
echo     Hub log    : %C3_DATA%\hub.log
echo.
echo   NOTE
echo   ----
echo     If 'c3' is not recognized, open a new terminal window or use:
echo     %C3_HOME%\c3.bat
echo.
pause
