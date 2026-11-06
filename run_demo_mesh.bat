@echo off
title 2-Peer Live Mesh Demonstration

echo ======================================================================
echo    STARTING 2-PEER LIVE P2P MESH DEMO (ALICE AND BOB)
echo ======================================================================
echo.

set PY=python
where python >nul 2>nul
if %ERRORLEVEL% neq 0 (
    set PY=py
)

echo [*] Starting Alice (Peer 1) on TCP:5555, UDP:5556...
start "Alice - Peer 1" %PY% peer.py --username Alice --tcp 5555 --udp 5556 --auto

echo [*] Waiting 2 seconds for Alice to initialize...
ping 127.0.0.1 -n 3 >nul

echo [*] Starting Bob (Peer 2) on TCP:5557, UDP:5558 and connecting to Alice...
start "Bob - Peer 2" %PY% peer.py --username Bob --tcp 5557 --udp 5558 --connect 127.0.0.1:5555 --auto

echo.
echo [OK] Both peers launched! Check your taskbar / screen for the two windows.
echo [OK] You can now test live video, audio, screen share, chat, and file sharing!
ping 127.0.0.1 -n 3 >nul
exit /b 0
