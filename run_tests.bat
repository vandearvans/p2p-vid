@echo off
title Automated Test Suite - P2P Collaboration System

echo ======================================================================
echo    RUNNING AUTOMATED P2P TEST SUITE (8 TEST CASES)
echo ======================================================================
echo.

set PY=python
where python >nul 2>nul
if %ERRORLEVEL% neq 0 (
    set PY=py
)

%PY% test_suite_p2p.py
echo.
pause
