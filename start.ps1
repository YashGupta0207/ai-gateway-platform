Write-Host "Starting all services in the background..." -ForegroundColor Green
docker compose up -d

Write-Host "Waiting a few seconds for the API to be ready..." -ForegroundColor Yellow
Start-Sleep -Seconds 5

Write-Host "Ensuring super admin user exists..." -ForegroundColor Green
docker compose exec -e SEED_ADMIN_EMAIL=you@example.com -e SEED_ADMIN_PASSWORD=change-me-now api python -m scripts.seed_super_admin

Write-Host ""
Write-Host "=======================================================" -ForegroundColor Cyan
Write-Host "✅ Everything is running!" -ForegroundColor Green
Write-Host "👉 Admin Portal: http://localhost:5173"
Write-Host "👉 API Backend:  http://localhost:8000"
Write-Host "👉 API Docs:     http://localhost:8000/docs"
Write-Host "=======================================================" -ForegroundColor Cyan
