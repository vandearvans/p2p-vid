# PowerShell 2-Peer Live Mesh Demonstration Launcher
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "   STARTING 2-PEER LIVE P2P MESH DEMO (ALICE AND BOB)" -ForegroundColor Yellow
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host ""

# 1. Start Alice (Peer 1)
Write-Host "[*] Launching Alice on TCP:5555, UDP:5556..." -ForegroundColor Green
Start-Process python -ArgumentList "peer.py --username Alice --tcp 5555 --udp 5556"

# 2. Wait 2 seconds
Start-Sleep -Seconds 2

# 3. Start Bob (Peer 2) connected to Alice
Write-Host "[*] Launching Bob on TCP:5557, UDP:5558 (Connected to Alice)..." -ForegroundColor Green
Start-Process python -ArgumentList "peer.py --username Bob --tcp 5557 --udp 5558 --connect 127.0.0.1:5555"

Write-Host ""
Write-Host "[OK] Both peer windows are now running on your desktop!" -ForegroundColor Cyan
Write-Host "[OK] You can now test live video, audio, screen share, chat, and files." -ForegroundColor Cyan
