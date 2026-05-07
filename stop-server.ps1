$connections = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue
if ($connections) {
    $connections | ForEach-Object {
        Write-Host "Stopping PID $($_.OwningProcess)"
        Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue
    }
    Write-Host "Server stopped."
} else {
    Write-Host "No server found on port 8000."
}
