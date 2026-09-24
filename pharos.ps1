[CmdletBinding()]
param(
  [string]$Title,
  [string]$Message = '',
  [string]$MessageFile,
  [string]$Source,
  [string]$Channel,
  [ValidateRange(-2, 2)][int]$Priority = 0,
  [string]$Url,
  [string]$UrlTitle,
  [string]$Sound,
  [switch]$Html,
  [switch]$DryRun,
  [switch]$Check
)

# One-shot CLI over Pharos.psm1, for anything that can run a command: a
# scheduled task action, a .bat, a git hook.
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File C:\path\to\Pharos\pharos.ps1 `
#       -Source archivist -Title 'Import stalled' -Message 'no new rows in 6h' -Priority 1
#
#   ...pharos.ps1 -Check        # masked config, send nothing
#
# -MessageFile for anything multi-line or quote-heavy: powershell -File strips
# embedded double quotes from inline native-exe arguments.
#
# EXIT CODES: 0 sent / muted / dry_run, 1 failed, 2 disabled.
# ASCII ONLY in this file.

$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'Pharos.psm1') -Force

if ($Check) {
  $status = Get-PharosStatus
  $status | Format-List
  if ($status.Enabled) { exit 0 } else { exit 2 }
}

if (-not $Title) {
  Write-Error 'Title is required unless -Check is given.'
  exit 1
}

if ($MessageFile) {
  if (-not (Test-Path $MessageFile)) {
    Write-Error "MessageFile not found: $MessageFile"
    exit 1
  }
  $Message = [System.IO.File]::ReadAllText($MessageFile, [System.Text.Encoding]::UTF8)
}

$params = @{ Title = $Title; Message = $Message; Priority = $Priority }
if ($Source) { $params['Source'] = $Source }
if ($Channel) { $params['Channel'] = $Channel }
if ($Url) { $params['Url'] = $Url }
if ($UrlTitle) { $params['UrlTitle'] = $UrlTitle }
if ($Sound) { $params['Sound'] = $Sound }
if ($Html) { $params['Html'] = $true }
if ($DryRun) { $params['DryRun'] = $true }

$result = Send-Pharos @params
Write-Host "[$($result.Status)] $($result.Response)"

switch ($result.Status) {
  'sent'     { exit 0 }
  'muted'    { exit 0 }
  'dry_run'  { exit 0 }
  'disabled' { exit 2 }
  default    { exit 1 }
}
