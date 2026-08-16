$ErrorActionPreference = 'Stop'

function Load-DotEnv([string]$Path) {
  $result = @{}
  Get-Content -Encoding UTF8 $Path | ForEach-Object {
    if ($_ -match '^([A-Z0-9_]+)=(.*)$') { $result[$matches[1]] = $matches[2] }
  }
  return $result
}

function Add-Result([string]$Service, [string]$Status, [string]$Detail, [int]$HttpStatus = 0) {
  $script:results.Add([pscustomobject]@{Service=$Service;Status=$Status;HttpStatus=$HttpStatus;Detail=$Detail})
}

function Invoke-SafeJson([string]$Service, [string]$Uri, [hashtable]$Headers = @{}) {
  try {
    $response = Invoke-WebRequest -UseBasicParsing -Uri $Uri -Headers $Headers -TimeoutSec 30
    $json = $response.Content | ConvertFrom-Json
    return @{Ok=$true; Http=[int]$response.StatusCode; Json=$json}
  } catch {
    $http = 0
    if ($_.Exception.Response) { $http = [int]$_.Exception.Response.StatusCode }
    Add-Result $Service 'FAIL' $_.Exception.Message $http
    return @{Ok=$false}
  }
}

function Get-DataGoResult([object]$Json) {
  $header = $Json.response.header
  if ($header.resultCode -and $header.resultCode -ne '00') { return "API_ERROR $($header.resultCode): $($header.resultMsg)" }
  $itemsNode = $Json.response.body.items
  $items = if ($itemsNode -is [System.Array]) { $itemsNode } else { $itemsNode.item }
  if ($null -eq $items) { return 'AUTH_OK records=0' }
  return "AUTH_OK records=$(@($items).Count)"
}

function Get-OdcloudResult([object]$Json) {
  if ($Json.currentCount -ne $null) { return "AUTH_OK records=$($Json.currentCount) total=$($Json.totalCount)" }
  if ($Json.data -ne $null) { return "AUTH_OK records=$(@($Json.data).Count)" }
  return 'UNEXPECTED_SCHEMA'
}

$scriptRootPath = if ($PSScriptRoot) { $PSScriptRoot } else { Join-Path (Get-Location) 'scripts' }
$envs = Load-DotEnv (Join-Path $scriptRootPath '..\.env')
$script:results = [System.Collections.Generic.List[object]]::new()

# odcloud 계열
$odcloud = @(
  @('LH 전국 단지', $envs.LH_COMPLEX_API_URL),
  @('승강기 건물좌표', $envs.ELEVATOR_BUILDING_COORD_API_URL),
  @('승강기 검사결과', $envs.ELEVATOR_INSPECTION_API_URL),
  @('승강기 시정권고', $envs.ELEVATOR_CORRECTIVE_ACTION_API_URL)
)
foreach ($entry in $odcloud) {
  $uri = "$($entry[1])?page=1&perPage=1&returnType=JSON&serviceKey=$($envs.DATA_GO_KR_SERVICE_KEY)"
  $call = Invoke-SafeJson $entry[0] $uri
  if ($call.Ok) {
    $detail = Get-OdcloudResult $call.Json
    Add-Result $entry[0] ($(if($detail -like 'AUTH_OK*'){'PASS'}else{'FAIL'})) $detail $call.Http
  }
}

# 공동주택 전체 목록, 여기서 실제 K-apt 코드를 확보
$listUri = "$($envs.MOLIT_COMPLEX_LIST_API_URL)?ServiceKey=$($envs.DATA_GO_KR_SERVICE_KEY)&pageNo=1&numOfRows=1&_type=json"
$listCall = Invoke-SafeJson '공동주택 단지목록' $listUri
$kaptCode = $null
if ($listCall.Ok) {
  $detail = Get-DataGoResult $listCall.Json
  $listItems = $listCall.Json.response.body.items
  $first = if ($listItems -is [System.Array]) { @($listItems)[0] } else { @($listItems.item)[0] }
  if ($first) { $kaptCode = $first.kaptCode }
  Add-Result '공동주택 단지목록' ($(if($detail -like 'AUTH_OK*'){'PASS'}else{'FAIL'})) $detail $listCall.Http
}

if ($kaptCode) {
  $basicUri = "$($envs.MOLIT_COMPLEX_BASIC_API_URL)?ServiceKey=$($envs.DATA_GO_KR_SERVICE_KEY)&kaptCode=$kaptCode&_type=json"
  $basicCall = Invoke-SafeJson '공동주택 기본정보' $basicUri
  if ($basicCall.Ok) { $detail=Get-DataGoResult $basicCall.Json; Add-Result '공동주택 기본정보' ($(if($detail -like 'AUTH_OK*'){'PASS'}else{'FAIL'})) $detail $basicCall.Http }

  $month = (Get-Date).AddMonths(-1).ToString('yyyyMM')
  $costUri = "$($envs.KAPT_MAINTENANCE_COST_API_URL)?ServiceKey=$($envs.DATA_GO_KR_SERVICE_KEY)&kaptCode=$kaptCode&searchDate=$month&_type=json"
  $costCall = Invoke-SafeJson '공동주택 승강기유지비' $costUri
  if ($costCall.Ok) { $detail=Get-DataGoResult $costCall.Json; Add-Result '공동주택 승강기유지비' ($(if($detail -like 'AUTH_OK*'){'PASS'}else{'FAIL'})) $detail $costCall.Http }
} else {
  Add-Result '공동주택 기본정보' 'SKIP' '단지목록에서 kaptCode 확보 실패'
  Add-Result '공동주택 승강기유지비' 'SKIP' '단지목록에서 kaptCode 확보 실패'
}

# 기상청 단기예보: 가장 최근 발표시각 사용, 서울 격자 60/127
$now = Get-Date
$baseHours = @(2,5,8,11,14,17,20,23)
$base = $baseHours | Where-Object { $_ -le $now.Hour } | Select-Object -Last 1
$baseDate = $now.ToString('yyyyMMdd')
if ($null -eq $base) { $base=23; $baseDate=$now.AddDays(-1).ToString('yyyyMMdd') }
$baseTime = '{0:00}00' -f $base
$forecastUri = "$($envs.KMA_VILAGE_FORECAST_API_URL)?ServiceKey=$($envs.KMA_SERVICE_KEY)&pageNo=1&numOfRows=10&dataType=JSON&base_date=$baseDate&base_time=$baseTime&nx=60&ny=127"
$forecastCall = Invoke-SafeJson '기상청 단기예보' $forecastUri
if ($forecastCall.Ok) { $detail=Get-DataGoResult $forecastCall.Json; Add-Result '기상청 단기예보' ($(if($detail -like 'AUTH_OK*'){'PASS'}else{'FAIL'})) $detail $forecastCall.Http }

$yesterday = (Get-Date).AddDays(-1).ToString('yyyyMMdd')
$asosUri = "$($envs.KMA_ASOS_HOURLY_API_URL)?ServiceKey=$($envs.KMA_SERVICE_KEY)&pageNo=1&numOfRows=1&dataType=JSON&dataCd=ASOS&dateCd=HR&startDt=$yesterday&startHh=00&endDt=$yesterday&endHh=23&stnIds=108"
$asosCall = Invoke-SafeJson '기상청 ASOS' $asosUri
if ($asosCall.Ok) { $detail=Get-DataGoResult $asosCall.Json; Add-Result '기상청 ASOS' ($(if($detail -like 'AUTH_OK*'){'PASS'}else{'FAIL'})) $detail $asosCall.Http }

# 서울시 3종
$seoulCalls = @(
  @('서울 강우량', "http://openapi.seoul.go.kr:8088/$($envs.SEOUL_RAINFALL_API_KEY)/json/ListRainfallService/1/5/"),
  @('서울 하수관로', "http://openapi.seoul.go.kr:8088/$($envs.SEOUL_SEWER_LEVEL_API_KEY)/json/DrainpipeMonitoringInfo/1/5/01/2022120614/2022120615"),
  @('서울 침수예상도', "http://openapi.seoul.go.kr:8088/$($envs.SEOUL_FLOOD_FORECAST_MAP_API_KEY)/json/floodingDs/1/5/")
)
foreach ($entry in $seoulCalls) {
  $call = Invoke-SafeJson $entry[0] $entry[1]
  if ($call.Ok) {
    $root = $call.Json.PSObject.Properties.Value | Select-Object -First 1
    $code = $root.RESULT.CODE
    $count = $root.list_total_count
    $ok = $code -eq 'INFO-000'
    Add-Result $entry[0] ($(if($ok){'PASS'}else{'FAIL'})) ($(if($ok){"AUTH_OK total=$count"}else{"API_ERROR ${code}: $($root.RESULT.MESSAGE)"})) $call.Http
  }
}

# 재난안전데이터공유플랫폼 침수흔적도 전용 키
if ([string]::IsNullOrWhiteSpace($envs.MOIS_FLOOD_TRACE_API_KEY)) {
  Add-Result '행안부 침수흔적도 API' 'SKIP' 'MOIS_FLOOD_TRACE_API_KEY 미입력'
} else {
  $moisKey = [uri]::EscapeDataString($envs.MOIS_FLOOD_TRACE_API_KEY)
  $moisUri = "$($envs.MOIS_FLOOD_TRACE_API_URL)?serviceKey=$moisKey&pageNo=1&numOfRows=1&returnType=json"
  $moisCall = Invoke-SafeJson '행안부 침수흔적도 API' $moisUri
  if ($moisCall.Ok) {
    $serialized = $moisCall.Json | ConvertTo-Json -Depth 20 -Compress
    $authError = @('SERVICE_KEY_IS_NOT_REGISTERED_ERROR','SERVICE_ACCESS_DENIED_ERROR','DEADLINE_HAS_EXPIRED_ERROR','UNREGISTERED_IP_ERROR','NO_SERVICE_KEY_ERROR') | Where-Object { $serialized -like "*$_*" } | Select-Object -First 1
    if ($authError) { Add-Result '행안부 침수흔적도 API' 'FAIL' "API_ERROR $authError" $moisCall.Http }
    else { Add-Result '행안부 침수흔적도 API' 'PASS' 'AUTH_OK (SN/FLDN_DOWA 속성 API)' $moisCall.Http }
  }
}

# NAVER Maps JS: 등록된 localhost referer로 SDK 인증 확인
$naverUri = "https://oapi.map.naver.com/openapi/v3/maps.js?ncpKeyId=$($envs.NAVER_MAP_CLIENT_ID)"
try {
  $naver = Invoke-WebRequest -UseBasicParsing -Uri $naverUri -Headers @{Referer='http://localhost:8501/'} -TimeoutSec 30
  $validJs = $naver.Content -match 'naver' -and $naver.Content -notmatch 'Authentication Failed'
  Add-Result 'NAVER Dynamic Map' ($(if($validJs){'PASS'}else{'FAIL'})) ($(if($validJs){'SDK_AUTH_OK'}else{'인증 실패 응답'})) ([int]$naver.StatusCode)
} catch {
  $http=0; if($_.Exception.Response){$http=[int]$_.Exception.Response.StatusCode}; Add-Result 'NAVER Dynamic Map' 'FAIL' $_.Exception.Message $http
}

# Anthropic 최소 호출
try {
  $headers = @{'x-api-key'=$envs.ANTHROPIC_API_KEY;'anthropic-version'='2023-06-01';'content-type'='application/json'}
  $body = @{model=$envs.CLAUDE_MODEL;max_tokens=1;messages=@(@{role='user';content='Reply OK'})} | ConvertTo-Json -Depth 6
  $response = Invoke-WebRequest -UseBasicParsing -Method Post -Uri 'https://api.anthropic.com/v1/messages' -Headers $headers -Body $body -TimeoutSec 30
  $json = $response.Content | ConvertFrom-Json
  Add-Result 'Anthropic Claude' 'PASS' "AUTH_MODEL_OK model=$($json.model)" ([int]$response.StatusCode)
} catch {
  $http=0; $detail=$_.Exception.Message
  if($_.Exception.Response){$http=[int]$_.Exception.Response.StatusCode}
  if($_.ErrorDetails.Message){try{$err=$_.ErrorDetails.Message|ConvertFrom-Json;$detail="$($err.error.type): $($err.error.message)"}catch{}}
  Add-Result 'Anthropic Claude' 'FAIL' $detail $http
}

$results | Format-Table -AutoSize
if ($results.Status -contains 'FAIL') { exit 2 }
