param(
  [string]$ApiBase = "http://localhost:8000",
  [Parameter(Mandatory=$true)][string]$CatalogId,
  [string]$ModuleCode = "SYS.3.2.2",
  [int]$PreviewLimit = 1,
  [int]$PollSeconds = 2,
  [int]$TimeoutSeconds = 900,
  [switch]$CheckDbUnchanged
)

$ErrorActionPreference = "Stop"

function Json($obj) { $obj | ConvertTo-Json -Depth 30 }

function Get-Json([string]$url) {
  Invoke-RestMethod -Method Get -Uri $url -ContentType "application/json"
}

function Post-Json([string]$url, $bodyObj) {
  $body = $bodyObj | ConvertTo-Json -Depth 30
  Invoke-RestMethod -Method Post -Uri $url -ContentType "application/json" -Body $body
}

function Require([bool]$cond, [string]$msg) {
  if (-not $cond) { throw "CHECK FAIL: $msg" }
}

Write-Host "=== Block 22 Smoke Test ==="
Write-Host "ApiBase: $ApiBase"
Write-Host "CatalogId: $CatalogId"
Write-Host "ModuleCode: $ModuleCode"
Write-Host "PreviewLimit: $PreviewLimit"
Write-Host "TimeoutSeconds: $TimeoutSeconds"
Write-Host ""

# 1) READY
Write-Host "1) GET /api/v1/ready"
$ready = Get-Json "$ApiBase/api/v1/ready"
Write-Host (Json $ready)

$map = @{}
foreach ($c in $ready.components) {
  $map[$c.name] = $c.status
}

Require ($map.ContainsKey("database")) "ready.components enthÃ¤lt database"
Require ($map["database"] -eq "ok") "database status ist ok"

Require ($map.ContainsKey("searxng")) "ready.components enthÃ¤lt searxng"
Require ($map["searxng"] -eq "ok") "searxng status ist ok"

Require ($map.ContainsKey("llm_llama3:8b")) "ready.components enthÃ¤lt llm_llama3:8b"
Require ($map["llm_llama3:8b"] -eq "ok") "llm_llama3:8b status ist ok"

Require ($map.ContainsKey("llm_llama3:70b")) "ready.components enthÃ¤lt llm_llama3:70b"
Require (@("ok","warn") -contains $map["llm_llama3:70b"]) "llm_llama3:70b status ist ok oder warn"

Write-Host "READY: PASS"
Write-Host ""

# 2) PREVIEW
Write-Host "2) GET /api/v1/bsi/catalogs/{catalog_id}/normalize/preview?limit=$PreviewLimit&module_code=$ModuleCode"
$previewUrl = "$ApiBase/api/v1/bsi/catalogs/$CatalogId/normalize/preview?limit=$PreviewLimit&module_code=$ModuleCode"
$preview = Get-Json $previewUrl
Write-Host (Json $preview)

Require ($null -ne $preview.items) "preview.items existiert"
Require ($preview.items.Count -ge 1) "preview.items enthÃ¤lt mindestens 1 Eintrag"
Require ($preview.items[0].PSObject.Properties.Name -contains "normalized_title") "preview item hat normalized_title"
Require ($preview.items[0].PSObject.Properties.Name -contains "normalized_description") "preview item hat normalized_description"

Write-Host "PREVIEW: PASS"
Write-Host ""

# Optional: DEV DB-Unchanged (vorher)
$beforeTitle = $null
$beforeDesc  = $null
$moduleId    = $null

if ($CheckDbUnchanged) {
  Write-Host "3) (optional) DB-Unchanged: hole Module-ID und Requirement vorher"
  $mods = Get-Json "$ApiBase/api/v1/bsi/catalogs/$CatalogId/modules"
  $target = $mods | Where-Object { $_.code -eq $ModuleCode } | Select-Object -First 1
  Require ($null -ne $target) "Modul $ModuleCode im Katalog gefunden"
  $moduleId = $target.id

  $reqsBefore = Get-Json "$ApiBase/api/v1/bsi/catalogs/$CatalogId/modules/$moduleId/requirements"
  Require ($reqsBefore.Count -ge 1) "requirements vor Job nicht leer"

  $beforeTitle = $reqsBefore[0].title
  $beforeDesc  = $reqsBefore[0].description

  Write-Host "Saved BEFORE sample:"
  Write-Host "title: $beforeTitle"
  Write-Host ""
}

# 4) START JOB
Write-Host "4) POST /api/v1/bsi/catalogs/{catalog_id}/normalize?module_code=$ModuleCode"
$startUrl = "$ApiBase/api/v1/bsi/catalogs/$CatalogId/normalize?module_code=$ModuleCode"
$job = Post-Json $startUrl @{}
Write-Host (Json $job)

Require ([bool]$job.id) "Job-ID vorhanden"
$jobId = $job.id
Write-Host "JOB START: PASS (job_id=$jobId)"
Write-Host ""

# 5) POLL JOB
Write-Host "5) Poll GET /api/v1/jobs/$jobId (bis completed/failed, max $TimeoutSeconds sec)"
$jobUrl = "$ApiBase/api/v1/jobs/$jobId"
$deadline = (Get-Date).AddSeconds($TimeoutSeconds)

while ($true) {
  $j = Get-Json $jobUrl
  $status = $j.status
  $prog = [math]::Round([double]$j.progress, 4)
  Write-Host ("- status={0} progress={1}" -f $status, $prog)

  if ($status -eq "completed" -or $status -eq "failed") {
    Write-Host ""
    Write-Host "FINAL JOB:"
    Write-Host (Json $j)

    if ($status -eq "failed") { throw "JOB FAILED: $($j.error)" }

    Require ($null -ne $j.result_data) "completed Job hat result_data"
    Require ($null -ne $j.result_data.summary) "result_data.summary vorhanden"
    Require ($null -ne $j.result_data.requirements) "result_data.requirements vorhanden"

    Write-Host "JOB: PASS"

    if ($CheckDbUnchanged) {
      Write-Host ""
      Write-Host "6) (optional) DB-Unchanged: Requirement nach Job holen und vergleichen"
      $reqsAfter = Get-Json "$ApiBase/api/v1/bsi/catalogs/$CatalogId/modules/$moduleId/requirements"
      Require ($reqsAfter.Count -ge 1) "requirements nach Job nicht leer"

      $afterTitle = $reqsAfter[0].title
      $afterDesc  = $reqsAfter[0].description

      if ($afterTitle -ne $beforeTitle -or $afterDesc -ne $beforeDesc) {
        throw "DB-UNCHANGED FAIL: title/description wurden in DEV geÃ¤ndert!"
      }

      Write-Host "DB-UNCHANGED: PASS"
    }

    break
  }

  if ((Get-Date) -gt $deadline) { throw "TIMEOUT: Job nach $TimeoutSeconds Sekunden nicht fertig." }
  Start-Sleep -Seconds $PollSeconds
}

Write-Host ""
Write-Host "=== Block 22 Smoke Test: DONE ==="
