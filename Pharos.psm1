# Pharos -- PowerShell binding. Same config, same policy.json, same title shape,
# same status contract as the Python package (pharos\push.py). No Python
# dependency on purpose: a watchdog paging about a broken Python must not need
# that Python to do it.
#
#   Import-Module C:\path\to\Pharos\Pharos.psm1
#   Send-Pharos -Source claude-rc -Title 'Spice is down' -Message $detail -Priority 1
#
# Or shell out to pharos.ps1 (same parameters) without importing anything.
#
# ASCII ONLY in this file (powershell.exe 5.1 reads BOM-less UTF-8 as ANSI).
# Glyphs are read from policy.json at send time, never written in here.
#
# TITLE:  "<glyph> <title>", no project label   (see push.py / README)
# STATUS: [pscustomobject]@{ Status; Response }
#         sent / muted / dry_run / disabled / failed

Set-StrictMode -Version Latest

$script:PushoverEndpoint = 'https://api.pushover.net/1/messages.json'
$script:DefaultTimeoutSec = 15
# Pushover rejects priority 2 unless told how hard to retry.
$script:EmergencyRetrySec = 60
$script:EmergencyExpireSec = 3600
$script:LogRotateBytes = 5MB
$script:Utf8NoBom = New-Object System.Text.UTF8Encoding $false
$script:Falsy = @('', '0', 'false', 'no', 'off')

function Get-PharosPath([string]$EnvName, [string]$Leaf) {
  $override = [Environment]::GetEnvironmentVariable($EnvName)
  if ($override) { return $override }
  return (Join-Path $PSScriptRoot $Leaf)
}

function Read-PharosJson([string]$Path) {
  if (-not (Test-Path $Path)) { return $null }
  try {
    return ([System.IO.File]::ReadAllText($Path, [System.Text.Encoding]::UTF8) | ConvertFrom-Json)
  } catch {
    return $null  # malformed is degraded, never a crash
  }
}

function Get-Prop($Object, [string]$Name) {
  if ($null -eq $Object) { return $null }
  if ($Object.PSObject.Properties.Name -contains $Name) { return $Object.$Name }
  return $null
}

function Get-PharosPolicy {
  $policy = Read-PharosJson (Get-PharosPath 'PHAROS_POLICY' 'policy.json')
  if ($policy -and (Get-Prop $policy 'channels')) { return $policy }
  # Fallback: ops only, glyph built from its code point so this file stays ASCII.
  return [pscustomobject]@{
    default_channel = 'ops'
    channels        = [pscustomobject]@{ ops = [pscustomobject]@{ glyph = [char]::ConvertFromUtf32(0x1F6E0); mutable = $false } }
    mutes           = @()
  }
}

function Resolve-PharosChannel([string]$Channel, $Policy) {
  $names = @($Policy.channels.PSObject.Properties.Name)
  $key = $Channel
  if (-not $key -or ($names -notcontains $key)) { $key = Get-Prop $Policy 'default_channel' }
  if (-not $key -or ($names -notcontains $key)) { $key = $names[0] }
  $spec = $Policy.channels.$key
  return [pscustomobject]@{ Key = $key; Glyph = [string](Get-Prop $spec 'glyph'); Mutable = [bool](Get-Prop $spec 'mutable') }
}

function Test-MuteLive($Mute) {
  $until = Get-Prop $Mute 'until'
  if ($until) {
    try {
      if ((Get-Date).Date -ge [datetime]::ParseExact($until, 'yyyy-MM-dd', $null)) { return $false }
    } catch { }
  }
  $override = Get-Prop $Mute 'override_env'
  if ($override) {
    $value = [Environment]::GetEnvironmentVariable($override)
    if ($value -and ($script:Falsy -notcontains $value.Trim().ToLower())) { return $false }
  }
  return $true
}

function Get-PharosMute([string]$Source, $Channel, $Policy) {
  # Never mutes a non-mutable channel: a dead pipeline must reach the phone.
  if (-not $Channel.Mutable) { return $null }
  foreach ($mute in @(Get-Prop $Policy 'mutes')) {
    if ($null -eq $mute) { continue }
    $ruleSource = [string](Get-Prop $mute 'source')
    if ($ruleSource -and ($ruleSource.ToLower() -ne ([string]$Source).ToLower())) { continue }
    if (@(Get-Prop $mute 'channels') -notcontains $Channel.Key) { continue }
    if (Test-MuteLive $mute) { return $mute }
  }
  return $null
}

function Format-PharosTitle {
  <#
    .SYNOPSIS
      "<glyph> <title>". Idempotent: an existing known glyph is not stamped
      twice. A leading "<source>: " label is removed -- projects are never
      named in the headline.
  #>
  param([string]$Title, [string]$Source, $Channel, $Policy)
  $body = $Title.Trim()
  foreach ($prop in $Policy.channels.PSObject.Properties) {
    $glyph = [string](Get-Prop $prop.Value 'glyph')
    if ($glyph -and $body.StartsWith($glyph, [StringComparison]::Ordinal)) {
      $body = $body.Substring($glyph.Length).TrimStart([char]0xFE0F).TrimStart()
      break
    }
  }
  if ($Source) {
    $body = [regex]::Replace($body, '^' + [regex]::Escape($Source) + '\s*:\s*', '', 'IgnoreCase')
  }
  if ($Channel.Glyph) { return "$($Channel.Glyph) $body" }
  return $body
}

function Format-PharosSpan {
  <#
    .SYNOPSIS
      Compact duration: "40s", "25m", "2h 15m", "3 days".
  #>
  param([double]$Seconds)
  $s = [int][Math]::Max(0, [Math]::Floor($Seconds))
  if ($s -lt 60) { return "${s}s" }
  $m = [int][Math]::Floor($s / 60)
  if ($m -lt 60) { return "${m}m" }
  $h = [int][Math]::Floor($m / 60)
  $m = $m % 60
  if ($h -lt 24) { if ($m) { return "${h}h ${m}m" } else { return "${h}h" } }
  $d = [int][Math]::Floor($h / 24)
  if ($d -eq 1) { return '1 day' }
  return "$d days"
}

function Format-PharosAgo {
  <#
    .SYNOPSIS
      Smart relative time: "just now", "25m ago", "3h ago", "yesterday",
      "4 days ago", then "Dec 26" (or "Dec 26 2025" in another year).
      Accepts a [datetime] or an ISO string.
  #>
  param($When, [datetime]$Now = (Get-Date))
  if ($When -is [string]) {
    $When = [datetime]::Parse($When, [Globalization.CultureInfo]::InvariantCulture, [Globalization.DateTimeStyles]::RoundtripKind)
  }
  if ($When.Kind -eq [DateTimeKind]::Utc) { $When = $When.ToLocalTime() }
  $secs = ($Now - $When).TotalSeconds
  if ($secs -lt 60) { return 'just now' }
  if ($secs -lt 3600) { return "$([int][Math]::Floor($secs / 60))m ago" }
  if ($secs -lt 21600 -or $When.Date -eq $Now.Date) { return "$([int][Math]::Floor($secs / 3600))h ago" }
  $days = [int]($Now.Date - $When.Date).TotalDays
  if ($days -le 1) { return 'yesterday' }
  if ($days -lt 7) { return "$days days ago" }
  $label = $When.ToString('MMM', [Globalization.CultureInfo]::InvariantCulture) + " $($When.Day)"
  if ($When.Year -eq $Now.Year) { return $label }
  return "$label $($When.Year)"
}

function Get-PharosAppTokens($Pushover) {
  # config.json pushover.apps: { "<source>": "<token>" }, keys matched case-insensitively.
  $map = @{}
  $apps = Get-Prop $Pushover 'apps'
  if ($apps) {
    foreach ($prop in $apps.PSObject.Properties) {
      if ($prop.Value) { $map[$prop.Name.ToLower()] = [string]$prop.Value }
    }
  }
  return $map
}

function Get-PharosCredentials([string]$Source) {
  # Each project can have its own Pushover app (that is what gives its pushes
  # their own icon), keyed by source in pushover.apps. Others use the default.
  $cfg = Read-PharosJson (Get-PharosPath 'PHAROS_CONFIG' 'config.json')
  $pushover = Get-Prop $cfg 'pushover'
  $user = $env:PHAROS_PUSHOVER_USER_KEY
  if (-not $user) { $user = Get-Prop $pushover 'user_key' }
  $token = $null
  if ($Source) { $token = (Get-PharosAppTokens $pushover)[$Source.ToLower()] }
  if (-not $token) { $token = $env:PHAROS_PUSHOVER_APP_TOKEN }
  if (-not $token) { $token = Get-Prop $pushover 'app_token' }
  return [pscustomobject]@{ User = $user; Token = $token }
}

function Get-PharosStatus {
  <#
    .SYNOPSIS
      Masked view of the resolved config. Safe to print and paste into logs.
  #>
  $creds = Get-PharosCredentials
  $policy = Get-PharosPolicy
  function Format-Mask([string]$Value) {
    if (-not $Value) { return '(unset)' }
    return '...' + $Value.Substring([Math]::Max(0, $Value.Length - 4))
  }
  $live = @(@(Get-Prop $policy 'mutes') | Where-Object { $_ -and (Test-MuteLive $_) } |
    ForEach-Object { "$($_.source): $(@($_.channels) -join ',')" })
  return [pscustomobject]@{
    ConfigFile  = (Get-PharosPath 'PHAROS_CONFIG' 'config.json')
    PolicyFile  = (Get-PharosPath 'PHAROS_POLICY' 'policy.json')
    LogFile     = (Get-PharosPath 'PHAROS_LOG' 'logs\pushes.jsonl')
    UserKey     = (Format-Mask $creds.User)
    AppToken    = (Format-Mask $creds.Token)
    ProjectApps = ((Get-PharosAppTokens (Get-Prop (Read-PharosJson (Get-PharosPath 'PHAROS_CONFIG' 'config.json')) 'pushover')).GetEnumerator() |
      Sort-Object Name | ForEach-Object { "$($_.Name) $(Format-Mask $_.Value)" }) -join ', '
    Enabled     = [bool]($creds.User -and $creds.Token)
    Channels    = (@($policy.channels.PSObject.Properties.Name) -join ', ')
    ActiveMutes = ($live -join '; ')
  }
}

function Write-PharosLog($Entry) {
  # Ledger append. Never throws.
  try {
    $path = Get-PharosPath 'PHAROS_LOG' 'logs\pushes.jsonl'
    $dir = Split-Path $path -Parent
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
    if ((Test-Path $path) -and ((Get-Item $path).Length -gt $script:LogRotateBytes)) {
      Move-Item -Force $path "$path.1"
    }
    $line = (ConvertTo-Json -InputObject $Entry -Compress) + "`n"
    [System.IO.File]::AppendAllText($path, $line, $script:Utf8NoBom)
  } catch { }
}

function ConvertTo-FormBody([hashtable]$Fields) {
  # Hand-encoded so non-ASCII (the glyphs) is always UTF-8 percent-encoded;
  # Windows PowerShell 5.1's hashtable -Body encoding is not trusted with it.
  return (($Fields.GetEnumerator() | ForEach-Object {
    [Uri]::EscapeDataString([string]$_.Key) + '=' + [Uri]::EscapeDataString([string]$_.Value)
  }) -join '&')
}

function Get-PharosEndpoint {
  # PHAROS_ENDPOINT overrides the Pushover URL (tests point it at a local server).
  if ($env:PHAROS_ENDPOINT) { return $env:PHAROS_ENDPOINT }
  return $script:PushoverEndpoint
}

function Invoke-PharosPost([hashtable]$Fields, [int]$TimeoutSec) {
  # Returns Status/Response/Transport. Transport = worth retrying later (DNS,
  # refused, timeout, 5xx); a 4xx means Pushover rejected the message itself.
  try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    $resp = Invoke-RestMethod -Uri (Get-PharosEndpoint) -Method Post -Body (ConvertTo-FormBody $Fields) `
      -ContentType 'application/x-www-form-urlencoded; charset=utf-8' -TimeoutSec $TimeoutSec
    $status = if ((Get-Prop $resp 'status') -eq 1) { 'sent' } else { 'failed' }
    return [pscustomobject]@{ Status = $status; Response = (ConvertTo-Json -InputObject $resp -Compress); Transport = $false }
  } catch {
    $transport = $true
    $ex = $_.Exception
    $httpResp = $null
    if ($ex.PSObject.Properties.Name -contains 'Response') { $httpResp = $ex.Response }
    if ($httpResp -and ($httpResp.PSObject.Properties.Name -contains 'StatusCode')) {
      $transport = ([int]$httpResp.StatusCode -ge 500)
    }
    return [pscustomobject]@{ Status = 'failed'; Response = "$($ex.GetType().Name): $($ex.Message)"; Transport = $transport }
  }
}

# ---- outbox: pushes held through a network outage (see pharos\outbox.py) ------
# Same file and format as the Python side: state\outbox.jsonl, one JSON object
# per line. A flush claims the file by renaming it, so two flushes at once can't
# deliver the same push twice. Held longer than MaxHeldHours = dropped.
$script:MaxHeldHours = 12

function Get-PharosOutboxPath {
  $base = if ($env:PHAROS_STATE_DIR) { $env:PHAROS_STATE_DIR } else { Join-Path $PSScriptRoot 'state' }
  return (Join-Path $base 'outbox.jsonl')
}

function Get-EpochNow { return ([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds() / 1000.0) }

function Add-PharosHeld($Entry) {
  try {
    $path = Get-PharosOutboxPath
    $dir = Split-Path $path -Parent
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
    [System.IO.File]::AppendAllText($path, (ConvertTo-Json -InputObject $Entry -Compress -Depth 5) + "`n", $script:Utf8NoBom)
    return $true
  } catch {
    return $false
  }
}

function Invoke-PharosFlush {
  <#
    .SYNOPSIS
      Deliver pushes held through a network outage. Never throws; returns counts.
  #>
  $counts = [ordered]@{ sent = 0; kept = 0; expired = 0; dropped = 0 }
  try {
    $path = Get-PharosOutboxPath
    if (-not (Test-Path $path)) { return [pscustomobject]$counts }
    $claimed = "$path.flushing-$PID-$([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds())"
    try { Move-Item -Path $path -Destination $claimed -ErrorAction Stop } catch { return [pscustomobject]$counts }
    $lines = @([System.IO.File]::ReadAllLines($claimed, [System.Text.Encoding]::UTF8) | Where-Object { $_.Trim() })
    $keep = @()
    $now = Get-EpochNow
    foreach ($line in $lines) {
      try { $e = $line | ConvertFrom-Json } catch { $counts.dropped++; continue }
      $age = $now - [double](Get-Prop $e 'queued_at')
      $src = [string](Get-Prop $e 'source')
      $log = [ordered]@{
        ts = (Get-Date).ToString('yyyy-MM-ddTHH:mm:ss'); lang = 'ps'
        source = $(if ($src) { $src } else { $null }); channel = (Get-Prop $e 'channel')
        priority = (Get-Prop $e 'priority'); status = ''; title = [string](Get-Prop $e 'title')
        message = [string](Get-Prop $e 'message'); detail = ''
      }
      if ($age -gt $script:MaxHeldHours * 3600) {
        $counts.expired++
        $log.status = 'expired'; $log.detail = "held $(Format-PharosSpan -Seconds $age), older than $($script:MaxHeldHours)h"
        Write-PharosLog $log
        continue
      }
      $creds = Get-PharosCredentials $src
      if (-not $creds.User -or -not $creds.Token) { $keep += $line; $counts.kept++; continue }
      $fields = @{}
      $held = Get-Prop $e 'fields'
      if ($held) { foreach ($prop in $held.PSObject.Properties) { $fields[$prop.Name] = [string]$prop.Value } }
      $fields['token'] = $creds.Token
      $fields['user'] = $creds.User
      $fields['title'] = [string](Get-Prop $e 'title')
      $fields['message'] = "$([string](Get-Prop $e 'message'))`nHeld $(Format-PharosSpan -Seconds $age)"
      $fields['timestamp'] = "$([int64][Math]::Floor([double](Get-Prop $e 'queued_at')))"
      $r = Invoke-PharosPost $fields $script:DefaultTimeoutSec
      if ($r.Status -eq 'sent') {
        $counts.sent++
        $log.status = 'sent'; $log.detail = "held $(Format-PharosSpan -Seconds $age)"
        Write-PharosLog $log
      } elseif ($r.Transport) {
        $keep += $line; $counts.kept++
      } else {
        $counts.dropped++
        $log.status = 'failed'; $log.detail = "held push rejected: $($r.Response)"
        Write-PharosLog $log
      }
    }
    if ($keep.Count -gt 0) {
      $dir = Split-Path $path -Parent
      if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
      [System.IO.File]::AppendAllText($path, (($keep -join "`n") + "`n"), $script:Utf8NoBom)
    }
    Remove-Item -Path $claimed -Force -ErrorAction SilentlyContinue
  } catch { }
  return [pscustomobject]$counts
}

function Send-Pharos {
  <#
    .SYNOPSIS
      Send one push. Never throws; returns Status/Response.
    .EXAMPLE
      Send-Pharos -Source claude-rc -Title 'Spice is down' -Message $detail -Priority 1
  #>
  [CmdletBinding()]
  param(
    [Parameter(Mandatory = $true)][string]$Title,
    [Parameter(Mandatory = $true)][AllowEmptyString()][string]$Message,
    [string]$Source,
    [string]$Channel,
    [ValidateRange(-2, 2)][int]$Priority = 0,
    [string]$Url,
    [string]$UrlTitle,
    [string]$Sound,
    [switch]$Html,
    [int]$Retry,
    [int]$Expire,
    [switch]$DryRun,
    [int]$TimeoutSec = 0,
    # On a network failure, keep the push and deliver it late. Only for callers
    # with no retry of their own. Status stays 'failed' (it did not leave the box).
    [switch]$Hold
  )

  if (-not $DryRun -and (Test-Path (Get-PharosOutboxPath))) { Invoke-PharosFlush | Out-Null }
  if ($TimeoutSec -le 0) { $TimeoutSec = $script:DefaultTimeoutSec }
  $policy = Get-PharosPolicy
  try {
    $ch = Resolve-PharosChannel $Channel $policy
    $fullTitle = Format-PharosTitle -Title $Title -Source $Source -Channel $ch -Policy $policy
  } catch {
    $ch = [pscustomobject]@{ Key = 'ops'; Glyph = ''; Mutable = $false }
    $fullTitle = $Title
  }

  $fields = @{ title = $fullTitle; message = $Message; priority = "$Priority" }
  if ($Url) {
    $fields['url'] = $Url
    if ($UrlTitle) { $fields['url_title'] = $UrlTitle }
  }
  if ($Html) { $fields['html'] = '1' }
  if ($Sound) { $fields['sound'] = $Sound }
  if ($Priority -eq 2) {
    $fields['retry'] = "$(if ($Retry -gt 0) { $Retry } else { $script:EmergencyRetrySec })"
    $fields['expire'] = "$(if ($Expire -gt 0) { $Expire } else { $script:EmergencyExpireSec })"
  }

  if ($DryRun) {
    return [pscustomobject]@{ Status = 'dry_run'; Response = (ConvertTo-Json -InputObject $fields -Compress) }
  }

  $creds = Get-PharosCredentials $Source
  $mute = Get-PharosMute $Source $ch $policy
  if ($mute) {
    $hint = if (Get-Prop $mute 'override_env') { " ($($mute.override_env)=1 to re-enable)" } else { '' }
    $result = [pscustomobject]@{ Status = 'muted'; Response = "$($ch.Key) pushes from $Source muted: $(Get-Prop $mute 'reason')$hint" }
  } elseif (-not $creds.User -or -not $creds.Token) {
    $result = [pscustomobject]@{ Status = 'disabled'; Response = "No Pushover credentials (PHAROS_PUSHOVER_* env or $(Get-PharosPath 'PHAROS_CONFIG' 'config.json'))" }
  } else {
    $heldFields = @{}
    foreach ($k in $fields.Keys) { if (@('title', 'message') -notcontains $k) { $heldFields[$k] = $fields[$k] } }
    $fields['token'] = $creds.Token
    $fields['user'] = $creds.User
    $post = Invoke-PharosPost $fields $TimeoutSec
    $result = [pscustomobject]@{ Status = $post.Status; Response = $post.Response }
    if ($post.Status -eq 'failed' -and $post.Transport -and $Hold) {
      $ok = Add-PharosHeld ([ordered]@{
        queued_at = (Get-EpochNow); source = $(if ($Source) { $Source } else { $null }); channel = $ch.Key
        priority = $Priority; title = $fullTitle; message = $Message; fields = $heldFields
      })
      if ($ok) { $result = [pscustomobject]@{ Status = 'failed'; Response = "held for retry: $($post.Response)" } }
    }
  }

  $detail = ''
  if ($result.Status -ne 'sent') { $detail = ([string]$result.Response).Substring(0, [Math]::Min(300, ([string]$result.Response).Length)) }
  Write-PharosLog ([ordered]@{
    ts       = (Get-Date).ToString('yyyy-MM-ddTHH:mm:ss')
    lang     = 'ps'
    source   = $(if ($Source) { $Source } else { $null })
    channel  = $ch.Key
    priority = $Priority
    status   = $result.Status
    title    = $fullTitle
    message  = $Message.Substring(0, [Math]::Min(500, $Message.Length))
    detail   = $detail
  })
  return $result
}

Export-ModuleMember -Function Send-Pharos, Invoke-PharosFlush, Get-PharosStatus, Format-PharosTitle, Format-PharosAgo, Format-PharosSpan, Get-PharosPolicy, Resolve-PharosChannel
