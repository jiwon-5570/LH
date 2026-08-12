$root = Resolve-Path (Join-Path $PSScriptRoot '..')
$registry = Get-Content -Raw -Encoding UTF8 (Join-Path $root 'config\data_sources.json') | ConvertFrom-Json
foreach ($dataset in $registry.datasets) {
  $directory = Join-Path $root ("data\incoming\" + $dataset.id)
  New-Item -ItemType Directory -Force $directory | Out-Null
}
Write-Host "$($registry.datasets.Count)개 데이터셋 입력 폴더 준비 완료"
