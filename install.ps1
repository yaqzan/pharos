[CmdletBinding()]
param(
  [switch]$Apply,
  [string]$PythonRoot = ''
)

# Makes `import pharos` work from any Python 3.11 process on this box and checks
# config.json. Dry-run by default; -Apply commits.
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File C:\path\to\Pharos\install.ps1
#   ...install.ps1 -Apply
#
# A .pth file in site-packages is a plain list of dirs added to sys.path at
# interpreter start. A venv built WITHOUT --system-site-packages will not see
# it: those callers add C:\path\to\Pharos to PYTHONPATH or use pharos.ps1.
#
# Also retires the .pth files of this package's earlier names (backed up to .retired\ first).
# ASCII ONLY in this file.

$ErrorActionPreference = 'Stop'

$here = $PSScriptRoot
if (-not $PythonRoot) {
  # The Python 3.11 that `py -3.11` launches; pass -PythonRoot to target another install.
  try { $PythonRoot = (& py -3.11 -c 'import sys; print(sys.base_prefix)' 2>$null | Select-Object -First 1) } catch { }
  if (-not $PythonRoot) { throw 'Python 3.11 not found via the py launcher; pass -PythonRoot <install dir>.' }
}
$sitePackages = Join-Path $PythonRoot 'Lib\site-packages'
$pthPath = Join-Path $sitePackages 'pharos.pth'
# Earlier names of this package: _ops\notify (ops_notify) and Tocsin.
$legacyPths = @('ops_notify.pth', 'tocsin.pth') | ForEach-Object { Join-Path $sitePackages $_ }
$configPath = Join-Path $here 'config.json'
$retired = Join-Path $here '.retired'

function Write-Plan([string]$Verb, [string]$Detail) {
  $tag = if ($Apply) { $Verb } else { "WOULD $Verb" }
  Write-Host ("{0,-14} {1}" -f $tag, $Detail)
}

Write-Host "pharos installer  (mode: $(if ($Apply) { 'APPLY' } else { 'DRY RUN -- pass -Apply to commit' }))"
Write-Host ''

# ---- 1. sys.path entry -------------------------------------------------------
if (-not (Test-Path $sitePackages)) {
  Write-Warning "site-packages not found: $sitePackages -- skipping the .pth step."
} else {
  $current = if (Test-Path $pthPath) { (Get-Content -Path $pthPath -Raw).Trim() } else { $null }
  if ($current -eq $here) {
    Write-Plan 'OK' "$pthPath already points at $here"
  } else {
    Write-Plan 'WRITE' "$pthPath -> $here"
    if ($Apply) { Set-Content -Path $pthPath -Value $here -Encoding ASCII }
  }
  foreach ($legacyPth in $legacyPths) {
    if (-not (Test-Path $legacyPth)) { continue }
    Write-Plan 'RETIRE' "$legacyPth (backup in $retired)"
    if ($Apply) {
      New-Item -ItemType Directory -Force -Path $retired | Out-Null
      Copy-Item $legacyPth (Join-Path $retired (Split-Path $legacyPth -Leaf)) -Force
      Remove-Item $legacyPth -Force
    }
  }
}

# ---- 2. config.json ----------------------------------------------------------
if (Test-Path $configPath) {
  Write-Plan 'OK' "$configPath exists -- left untouched (never overwrite a live credential file)"
} else {
  Write-Warning "$configPath is missing. Copy config.example.json to config.json and fill in your keys (it is gitignored)."
}

# ---- 3. Verify ---------------------------------------------------------------
Write-Host ''
if (-not $Apply) {
  Write-Host 'Dry run complete. Re-run with -Apply to write and verify both bindings.'
  return
}

Write-Host 'Verifying PowerShell binding...'
& (Join-Path $here 'pharos.ps1') -Check
$psOk = ($LASTEXITCODE -eq 0)

Write-Host 'Verifying Python binding (from C:\, so the .pth is doing the work, not cwd)...'
$pythonExe = Join-Path $PythonRoot 'python.exe'
$pyOk = $false
if (Test-Path $pythonExe) {
  Push-Location 'C:\'
  try {
    & $pythonExe -m pharos --check
    $pyOk = ($LASTEXITCODE -eq 0)
  } finally {
    Pop-Location
  }
} else {
  Write-Warning "python.exe not found at $pythonExe"
}

Write-Host ''
if ($psOk -and $pyOk) {
  Write-Host 'Both bindings resolve credentials.'
} else {
  Write-Warning "Verification incomplete (powershell ok: $psOk, python ok: $pyOk)."
}
