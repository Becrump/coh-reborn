# Bench for AI talking on this PC (CoH Reborn). Runs outside the game; touches no game files.
#
#   powershell -ExecutionPolicy Bypass -File bench_talk.ps1                  # both models, 3 threads
#   powershell -ExecutionPolicy Bypass -File bench_talk.ps1 -Models 4b -Threads 4
#   powershell -ExecutionPolicy Bypass -File bench_talk.ps1 -Load 300        # keep talking for 5 min
#
# First run downloads into tools\talk\.cache (about 4.5 GB, kept out of git):
#   - llama.cpp's Windows CPU build (llama-server.exe), latest release from GitHub
#   - Qwen3 1.7B (Q8, 1.8 GB) and Qwen3 4B (Q4_K_M, 2.5 GB), Apache-2.0, from Hugging Face
# Then for each model: starts llama-server on 127.0.0.1:8090 with -Threads CPU threads,
# plays tools\talk\mock_script.json through talk_sim.py, and appends one SUMMARY line per
# model to bench_talk_results.txt. Full transcripts: bench_talk_<model>.log / .jsonl.
#
# -Load N keeps the mock conversations looping for N seconds so you can start the game
# (or tools\build\bench_lowend.cmd) at the same time and see the frame-rate cost.
# Nothing uses the graphics card. Needs Python 3 on PATH (already used by tools\rules).
param(
  [string[]]$Models = @("1.7b", "4b"),
  [int]$Threads = 3,
  [int]$Load = 0,
  [int]$Port = 8090
)
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$cache = Join-Path $here ".cache"
New-Item -ItemType Directory -Force -Path $cache | Out-Null
$results = Join-Path $here "bench_talk_results.txt"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$modelFiles = @{
  "1.7b" = @{ file = "Qwen3-1.7B-Q8_0.gguf";   url = "https://huggingface.co/Qwen/Qwen3-1.7B-GGUF/resolve/main/Qwen3-1.7B-Q8_0.gguf" }
  "4b"   = @{ file = "Qwen3-4B-Q4_K_M.gguf";   url = "https://huggingface.co/Qwen/Qwen3-4B-GGUF/resolve/main/Qwen3-4B-Q4_K_M.gguf" }
}

# --- llama.cpp server -------------------------------------------------------------
$server = Get-ChildItem -Path (Join-Path $cache "llama") -Recurse -Filter "llama-server.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $server) {
  Write-Host "Finding the latest llama.cpp Windows CPU build..."
  $rel = Invoke-RestMethod "https://api.github.com/repos/ggml-org/llama.cpp/releases/latest" -Headers @{ "User-Agent" = "coh-reborn-bench" }
  $asset = $rel.assets | Where-Object { $_.name -match "bin-win-cpu-x64\.zip$" } | Select-Object -First 1
  if (-not $asset) { throw "No win-cpu-x64 build in llama.cpp release $($rel.tag_name)" }
  $zip = Join-Path $cache $asset.name
  Write-Host "Downloading $($asset.name) ($($rel.tag_name))..."
  Invoke-WebRequest $asset.browser_download_url -OutFile $zip -UseBasicParsing
  Expand-Archive $zip -DestinationPath (Join-Path $cache "llama") -Force
  $server = Get-ChildItem -Path (Join-Path $cache "llama") -Recurse -Filter "llama-server.exe" | Select-Object -First 1
  Add-Content $results ("{0}  llama.cpp {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm"), $rel.tag_name)
}

$cpu = (Get-CimInstance Win32_Processor | Select-Object -First 1).Name.Trim()
$editor = if (Get-Process UnrealEditor -ErrorAction SilentlyContinue) { "editor running" } else { "editor closed" }

foreach ($m in $Models) {
  $info = $modelFiles[$m]
  if (-not $info) { Write-Warning "Unknown model '$m' (use 1.7b or 4b)"; continue }
  $gguf = Join-Path $cache $info.file
  if (-not (Test-Path $gguf)) {
    Write-Host "Downloading $($info.file)..."
    Invoke-WebRequest $info.url -OutFile "$gguf.part" -UseBasicParsing
    Move-Item "$gguf.part" $gguf -Force
  }
  Write-Host "Starting llama-server with $m on $Threads threads..."
  $p = Start-Process -FilePath $server.FullName -PassThru -WindowStyle Hidden `
       -ArgumentList @("-m", "`"$gguf`"", "-t", $Threads, "-c", "4096", "--host", "127.0.0.1", "--port", $Port, "-np", "1") `
       -RedirectStandardError (Join-Path $here "bench_talk_server_$m.log")
  try {
    $p.PriorityClass = "BelowNormal"   # the game's threads come first, as planned for the real thing
    $ok = $false
    for ($i = 0; $i -lt 120; $i++) {
      Start-Sleep -Seconds 1
      try { if ((Invoke-RestMethod "http://127.0.0.1:$Port/health" -TimeoutSec 2).status -eq "ok") { $ok = $true; break } } catch {}
    }
    if (-not $ok) { throw "llama-server did not come up; see bench_talk_server_$m.log" }
    $log = Join-Path $here "bench_talk_$m.log"
    $jsonl = Join-Path $here "bench_talk_$m.jsonl"
    $deadline = (Get-Date).AddSeconds($Load)
    do {
      python -I (Join-Path $here "talk_sim.py") --script (Join-Path $here "mock_script.json") `
        --server "http://127.0.0.1:$Port" --seed 4 --log $jsonl *>&1 | Tee-Object -FilePath $log -Append
      $summary = Get-Content $log | Where-Object { $_ -like "SUMMARY*" } | Select-Object -Last 1
      Add-Content $results ("{0}  {1}  threads={2}  {3}  {4}  {5}" -f (Get-Date -Format "yyyy-MM-dd HH:mm"), $cpu, $Threads, $editor, $m, $summary)
    } while ((Get-Date) -lt $deadline)
  } finally {
    if (-not $p.HasExited) { Stop-Process -Id $p.Id -Force }
  }
}
Write-Host "`nResults:"
Get-Content $results | Select-Object -Last 6
