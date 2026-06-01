# Atlas Infrastructure Startup Script
# Prerequisites: Docker Desktop must be running

Write-Host "Atlas Infrastructure Startup" -ForegroundColor Cyan
Write-Host "=============================" -ForegroundColor Cyan
Write-Host ""

# Check if Docker is running
Write-Host "Checking Docker daemon..." -ForegroundColor Yellow
try {
    docker ps | Out-Null
    Write-Host "[OK] Docker daemon is running" -ForegroundColor Green
} catch {
    Write-Host "[ERROR] Docker daemon is not running. Please start Docker Desktop." -ForegroundColor Red
    exit 1
}

# Start services
Write-Host ""
Write-Host "Starting Neo4j and PostgreSQL..." -ForegroundColor Yellow
docker-compose up -d

# Wait for services to be healthy
Write-Host ""
Write-Host "Waiting for services to be ready..." -ForegroundColor Yellow
Start-Sleep -Seconds 10

# Verify Neo4j
Write-Host ""
Write-Host "Verifying Neo4j connectivity..." -ForegroundColor Cyan
$neo4j_running = $false
for ($i = 1; $i -le 6; $i++) {
    try {
        $response = curl.exe -s -f "http://localhost:7474" -o $null -w "%{http_code}"
        if ($response -eq "200") {
            Write-Host "[OK] Neo4j HTTP is reachable on localhost:7474" -ForegroundColor Green
            Write-Host "     Browser: http://localhost:7474" -ForegroundColor Green
            Write-Host "     Credentials: neo4j / atlas_password_123" -ForegroundColor Gray
            $neo4j_running = $true
            break
        }
    } catch {
        # Continue to retry
    }
    if ($i -lt 6 -and -not $neo4j_running) {
        Write-Host "     Attempt $i/6: Neo4j not ready yet, waiting..." -ForegroundColor Gray
        Start-Sleep -Seconds 5
    }
}

if (-not $neo4j_running) {
    Write-Host "[ERROR] Neo4j is not responding after waiting" -ForegroundColor Red
}

# Verify PostgreSQL
Write-Host ""
Write-Host "Verifying PostgreSQL connectivity..." -ForegroundColor Cyan
$postgres_running = $false

# Try docker exec method
try {
    docker-compose exec -T postgres pg_isready -U atlas_user -d atlas 2>&1 | Out-Null
    Write-Host "[OK] PostgreSQL is reachable on localhost:5432" -ForegroundColor Green
    Write-Host "     Database: atlas" -ForegroundColor Green
    Write-Host "     User: atlas_user / atlas_password_123" -ForegroundColor Gray
    $postgres_running = $true
} catch {
    Write-Host "[ERROR] PostgreSQL is not responding" -ForegroundColor Red
}

# Summary
Write-Host ""
Write-Host "=============================" -ForegroundColor Cyan
Write-Host "Infrastructure Status:" -ForegroundColor Cyan

if ($neo4j_running) {
    Write-Host "  Neo4j:      [OK] Running" -ForegroundColor Green
} else {
    Write-Host "  Neo4j:      [ERROR] Not responding" -ForegroundColor Red
}

if ($postgres_running) {
    Write-Host "  PostgreSQL: [OK] Running" -ForegroundColor Green
} else {
    Write-Host "  PostgreSQL: [ERROR] Not responding" -ForegroundColor Red
}

Write-Host ""
Write-Host "Container Status:" -ForegroundColor Cyan
docker-compose ps

Write-Host ""
Write-Host "Logs:" -ForegroundColor Cyan
Write-Host "  View Neo4j logs:      docker-compose logs neo4j" -ForegroundColor Gray
Write-Host "  View PostgreSQL logs: docker-compose logs postgres" -ForegroundColor Gray
Write-Host "  View all logs:        docker-compose logs" -ForegroundColor Gray
Write-Host ""
Write-Host "Stop services:" -ForegroundColor Cyan
Write-Host "  docker-compose down" -ForegroundColor Gray
