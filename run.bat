@echo off
setlocal enabledelayedexpansion
title P2P Multi-User Collaboration System - Launcher

cls
echo ======================================================================
echo       P2P MULTI-USER COLLABORATION SYSTEM (COMPUTER NETWORKS)
echo ======================================================================
echo   Pure Peer-to-Peer Architecture (No Central Server Required)
echo   Integrated Backend Networking (TCP/UDP) + Modern GUI Frontend
echo ======================================================================
echo.

where python >nul 2>nul
if %ERRORLEVEL% neq 0 (
    where py >nul 2>nul
    if %ERRORLEVEL% neq 0 (
        echo [ERROR] Python is not installed or not in PATH!
        echo Please install Python 3.8 - 3.14 from https://python.org
        pause
        exit /b 1
    ) else (
        set PYTHON_CMD=py
    )
) else (
    set PYTHON_CMD=python
)

echo [OK] Python detected:
!PYTHON_CMD! --version
echo.

echo [*] Checking dependencies from requirements.txt...
!PYTHON_CMD! -c "import cv2, PIL, mss, numpy, sounddevice" >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [*] Installing required packages...
    !PYTHON_CMD! -m pip install -r requirements.txt
    if %ERRORLEVEL% neq 0 (
        echo [WARNING] Some dependencies failed to install. Continuing anyway...
    )
) else (
    echo [OK] All core dependencies verified.
)
echo.

echo Select launch mode:
echo   [1] Start Standard P2P Collaboration Node (Single User GUI)
echo   [2] Start 2-Peer Live Mesh Demo (Alice and Bob auto-connected on Localhost)
echo   [3] Start 3-Peer Full Mesh Demo (Alice, Bob and Charlie auto-meshed)
echo   [4] Run Automated Network Test Suite (8 Test Cases)
echo   [5] Start Headless / CLI Peer Node
echo.
set /p choice="Enter choice (1-5) [Default is 1]: "

if "%choice%"=="" set choice=1

if "%choice%"=="1" (
    echo.
    echo [*] Starting P2P Collaboration App (Frontend + Backend)...
    start "P2P Collaboration Node" !PYTHON_CMD! peer.py
    exit /b 0
)

if "%choice%"=="2" (
    echo.
    echo [*] Launching 2-Peer Live Mesh Demonstration...
    echo [*] Starting Peer 1 (Alice) on TCP 5555 / UDP 5556...
    start "Alice - Peer 1" !PYTHON_CMD! peer.py --username Alice --tcp 5555 --udp 5556 --auto
    ping 127.0.0.1 -n 3 >nul
    echo [*] Starting Peer 2 (Bob) on TCP 5557 / UDP 5558 connected to Alice...
    start "Bob - Peer 2" !PYTHON_CMD! peer.py --username Bob --tcp 5557 --udp 5558 --connect 127.0.0.1:5555 --auto
    echo [OK] Both peers running and interconnected!
    exit /b 0
)

if "%choice%"=="3" (
    echo.
    echo [*] Launching 3-Peer Full Mesh Demonstration...
    echo [*] Starting Peer 1 (Alice) on TCP 5555 / UDP 5556...
    start "Alice - Peer 1" !PYTHON_CMD! peer.py --username Alice --tcp 5555 --udp 5556 --auto
    ping 127.0.0.1 -n 3 >nul
    echo [*] Starting Peer 2 (Bob) on TCP 5557 / UDP 5558 connected to Alice...
    start "Bob - Peer 2" !PYTHON_CMD! peer.py --username Bob --tcp 5557 --udp 5558 --connect 127.0.0.1:5555 --auto
    ping 127.0.0.1 -n 3 >nul
    echo [*] Starting Peer 3 (Charlie) on TCP 5559 / UDP 5560 connected to Bob (PEX auto-meshes to Alice)...
    start "Charlie - Peer 3" !PYTHON_CMD! peer.py --username Charlie --tcp 5559 --udp 5560 --connect 127.0.0.1:5557 --auto
    echo [OK] 3-Peer Full Mesh online!
    exit /b 0
)

if "%choice%"=="4" (
    echo.
    echo [*] Running automated test suite...
    !PYTHON_CMD! test_suite_p2p.py
    echo.
    pause
    exit /b 0
)

if "%choice%"=="5" (
    echo.
    echo [*] Starting Headless CLI Peer Node...
    !PYTHON_CMD! cli_peer.py
    exit /b 0
)

echo [!] Invalid choice, launching default P2P Node...
start "P2P Collaboration Node" !PYTHON_CMD! peer.py
exit /b 0
