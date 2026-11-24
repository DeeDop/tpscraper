param(
    [ValidateRange(1,60)][int]$IntervalSeconds = 5,
    [ValidateRange(0,168)][double]$Hours = 6,
    [ValidateRange(1024,65535)][int]$Port = 8789,
    [string]$Output = "$env:USERPROFILE\Downloads\tpscraper_soak.jsonl"
)
# Read-only local API/process monitor. No tokens, cookies or market orders.
$ErrorActionPreference = 'Stop'
$base = "http://127.0.0.1:$Port"
$folder = Split-Path -Parent $Output
if ($folder) { New-Item -ItemType Directory -Force -Path $folder | Out-Null }
$clock = [System.Diagnostics.Stopwatch]::StartNew()
$prevCpu = $null
$prevElapsed = $null
$prevProcess = $null
Write-Host "Recording health and resource samples to $Output. Ctrl+C stops monitoring only."
while ($Hours -eq 0 -or $clock.Elapsed.TotalHours -lt $Hours) {
    $row = [ordered]@{ utc = [DateTime]::UtcNow.ToString('o'); elapsed_s = [math]::Round($clock.Elapsed.TotalSeconds,3) }
    try {
        $h = Invoke-RestMethod "$base/api/health" -TimeoutSec 5
        $d = Invoke-RestMethod "$base/api/diagnostics" -TimeoutSec 5
        $row.health = $h
        $row.streams = $d.streams
        $process = Get-Process -Id $h.process_id -ErrorAction Stop
        $cpu = $process.TotalProcessorTime.TotalSeconds
        $elapsed = $clock.Elapsed.TotalSeconds
        $cpuPct = $null
        if ($prevProcess -eq $process.Id -and $null -ne $prevCpu -and $elapsed -gt $prevElapsed) {
            $cpuPct = [math]::Round(100*($cpu-$prevCpu)/($elapsed-$prevElapsed)/[Environment]::ProcessorCount,2)
        }
        $row.resources = [ordered]@{ pid=$process.Id; working_set_mb=[math]::Round($process.WorkingSet64/1MB,2); private_mb=[math]::Round($process.PrivateMemorySize64/1MB,2); threads=$process.Threads.Count; handles=$process.HandleCount; cpu_pct=$cpuPct }
        $prevProcess=$process.Id; $prevCpu=$cpu; $prevElapsed=$elapsed
        Write-Host ("{0} | connected={1} | fresh={2}/{3} | books={4} | RAM={5}MB | threads={6}" -f $row.utc,$h.connected,$h.timestamped_live_count,$h.instruments,$h.fresh_book_count,$row.resources.private_mb,$row.resources.threads)
    } catch {
        $row.error = $_.Exception.GetType().Name
        Write-Host "$($row.utc) | sample unavailable" -ForegroundColor Yellow
        $prevCpu=$null
    }
    $row | ConvertTo-Json -Depth 20 -Compress | Add-Content -LiteralPath $Output -Encoding UTF8
    Start-Sleep -Seconds $IntervalSeconds
}
Write-Host "Monitoring complete: $Output"
