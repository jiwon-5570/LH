param(
  [switch]$ContinueOnError
)
$ErrorActionPreference = 'Stop'
$root = Resolve-Path (Join-Path $PSScriptRoot '..')
$registry = Get-Content -Raw -Encoding UTF8 (Join-Path $root 'config\data_sources.json') | ConvertFrom-Json
foreach ($dataset in $registry.datasets) {
  $drop = Join-Path $root ("data\incoming\" + $dataset.id)
  if (-not (Test-Path $drop)) { New-Item -ItemType Directory -Force $drop | Out-Null }
  $files = Get-ChildItem -LiteralPath $drop -File | Where-Object { $_.Name -ne 'README.md' }
  foreach ($file in $files) {
    Write-Host "[$($dataset.id)] $($file.Name)"
    try { & python -m backend.app.collectors.cli ingest $dataset.id --file $file.FullName }
    catch { if (-not $ContinueOnError) { throw }; Write-Error $_ -ErrorAction Continue }
  }
}
