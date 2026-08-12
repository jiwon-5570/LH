param(
  [string]$OutputDocx = "artifacts\reports\LH-PREDICT_데이터도입_준비보고서_20260807.docx",
  [string]$OutputPdf = "artifacts\reports\LH-PREDICT_데이터도입_준비보고서_20260807.pdf"
)
$ErrorActionPreference = 'Stop'
$root = if ($PSScriptRoot) { Resolve-Path (Join-Path $PSScriptRoot '..') } else { Resolve-Path (Get-Location) }
$template = 'C:\Users\kangj\.codex\plugins\cache\openai-curated-remote\openai-templates\0.1.1\skills\artifact-template-design-report\assets\reference.docx'
$docx = [System.IO.Path]::GetFullPath((Join-Path $root $OutputDocx))
$pdf = [System.IO.Path]::GetFullPath((Join-Path $root $OutputPdf))
New-Item -ItemType Directory -Force ([System.IO.Path]::GetDirectoryName($docx)) | Out-Null
Copy-Item -LiteralPath $template -Destination $docx -Force

$replacements = [ordered]@{
  'Report title' = 'LH-PREDICT 데이터 도입 준비 보고서'
  'Short subtitle describing the report up to two lines of text' = '확보 완료된 공공 API·파일데이터 15종의 즉시 투입 구조와 적용 절차'
  'Prepared by [Author]' = 'Prepared for LH-PREDICT'
  '[Month YYYY]' = '2026년 8월 7일'
  'Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat.' = 'LH-PREDICT에 필요한 15개 데이터셋을 파일 또는 API로 즉시 투입할 수 있도록 데이터 소스 레지스트리, 입력 드롭존, 공통 수집 파이프라인과 품질검사 이력을 구현했다. 운영 데이터가 없을 때 임의 수치로 대체하지 않는 원칙은 유지된다.'
  'Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla pariatur. Excepteur sint occaecat cupidatat non proident, sunt in culpa qui officia deserunt mollit anim id est laborum.' = '사용자는 데이터셋별 폴더에 파일을 넣거나 환경변수에 승인된 API URL과 키를 입력한 뒤 단일 CLI로 수집할 수 있다. 실제 응답 샘플 투입 후 원본 컬럼 별칭, 단위, 좌표계와 레코드 경로를 최종 확정해야 한다.'
  'At a glance' = '한눈에 보기'
  'Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt.' = '15개 데이터셋 등록 · 파일/API 통합 입력 · 실행별 원본 보존'
  'Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat.' = '필수값·좌표·식별자 중복 검사 · 실패 행 quarantine 분리'
  'Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla pariatur.' = '수집 실행과 품질 결과 DB 기록 · API 조회 지원'
  'Introduction' = '도입 배경'
  'Sed ut perspiciatis unde omnis iste natus error sit voluptatem accusantium doloremque laudantium, totam rem aperiam, eaque ipsa quae ab illo inventore veritatis et quasi architecto beatae vitae dicta sunt explicabo.' = '확보 데이터는 LH 단지, 공동주택 기본·관리비, 기상·강우·하수 수위, 침수 공간정보, DEM, 승강기 설치·좌표·검사·시정권고로 구성된다. 형식과 제공기관이 달라 공통 메타데이터와 검증 절차가 필요하다.'
  'Nemo enim ipsam voluptatem quia voluptas sit aspernatur aut odit aut fugit, sed quia consequuntur magni dolores eos qui ratione voluptatem sequi nesciunt.' = '이번 구현은 원본을 변경하지 않고 raw, staging, processed, quarantine 계층으로 분리한다. 데이터의 존재 여부와 품질을 모델·화면 활성 조건으로 사용한다.'
  'Key findings' = '핵심 결과'
  'Neque porro quisquam est, qui dolorem ipsum quia dolor sit amet, consectetur, adipisci velit, sed quia non numquam eius modi tempora incidunt ut labore et dolore magnam aliquam quaerat voluptatem.' = '모든 데이터셋에 고정 ID, 입력 방식, 허용 형식, API 환경변수, 필수 표준 컬럼과 원본 컬럼 별칭이 정의됐다. 동일한 CLI가 API와 파일을 구분해 원본 보존부터 품질검사까지 수행한다.'
  'Context and conditions' = '적용 조건'
  'Ut enim ad minima veniam, quis nostrum exercitationem ullam corporis suscipit laboriosam, nisi ut aliquid ex ea commodi consequatur.' = 'API형 데이터는 실제 승인 URL과 키가 필요하다. 파일형 데이터는 지정 드롭존에 원본을 그대로 넣는다. 공간정보와 DEM은 CRS, geometry, 범위와 NoData를 확인해야 한다.'
  'Patterns in the evidence' = '데이터 구조 패턴'
  'Quis autem vel eum iure reprehenderit qui in ea voluptate velit esse quam nihil molestiae consequatur, vel illum qui dolorem eum fugiat.' = '단지코드·K-apt 코드·승강기번호가 핵심 연결키이며, 주소와 좌표는 보조 매칭에 사용된다. 기상·강우·수위는 관측시각, 예보는 발표시각과 대상시각을 분리해야 한다.'
  'Key takeaway. At vero eos et accusamus et iusto odio dignissimos ducimus qui blanditiis praesentium voluptatum deleniti atque corrupti.' = '핵심 판단. 실제 파일 한 건과 API 응답 한 페이지를 먼저 투입해 컬럼명·단위·시간대·좌표계를 확정한 뒤 전체 적재를 실행한다.'
  'Implications' = '운영 영향'
  'Et harum quidem rerum facilis est et expedita distinctio. Nam libero tempore, cum soluta nobis est eligendi optio cumque nihil impedit.' = '데이터 품질 결과가 예측 가능 여부를 제어한다. 격리 데이터는 자동 수정하지 않으며, 정제 규칙과 근거를 기록한 뒤 재처리한다.'
  'Recommendations' = '권고 실행 순서'
  'Temporibus autem quibusdam et aut officiis debitis aut rerum necessitatibus saepe eveniet ut et voluptates repudiandae sint et molestiae non recusandae.' = '다음 순서로 실제 데이터를 적용하면 컬럼 오매핑과 대량 격리를 최소화할 수 있다.'
  'Clarify the objective. Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.' = '1. 입력 계약 확인. 각 데이터셋의 실제 파일 헤더와 API 응답 레코드 경로를 레지스트리 별칭과 대조한다.'
  'Sequence the work. Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat.' = '2. 소량 검증. 파일 1개 또는 API 1페이지를 수집해 정상·격리 건수, 단위, CRS와 기준시각을 확인한다.'
  'Review the outcome. Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla pariatur.' = '3. 전체 적용. 일괄 적재 후 품질 API를 검토하고 단지·승강기 매칭의 수동 검토 대상을 확정한다.'
  'Conclusion' = '결론'
  'Itaque earum rerum hic tenetur a sapiente delectus, ut aut reiciendis voluptatibus maiores alias consequatur aut perferendis doloribus asperiores repellat.' = '저장소는 15개 데이터셋을 받을 준비가 완료됐다. 파일은 data/incoming의 데이터셋별 폴더에 넣고 API는 .env에 URL과 키를 설정하면 된다.'
  'Excepteur sint occaecat cupidatat non proident, sunt in culpa qui officia deserunt mollit anim id est laborum.' = '실제 응답을 확인하기 전에는 예측·보고서·AI 기능을 활성화하지 않는다. 데이터 출처와 기준시각을 추적할 수 있는 상태에서만 후속 피처 생성과 모델 검증을 진행한다.'
  'Appendix' = '부록'
  'Notes' = '실행 명령'
  'Lorem ipsum dolor sit amet, consectetur adipiscing elit. Integer nec odio. Praesent libero. Sed cursus ante dapibus diam.' = '파일: python -m backend.app.collectors.cli ingest <dataset_id> --file <path>'
  'Suspendisse potenti. Nunc feugiat mi a tellus consequat imperdiet. Vestibulum sapien. Proin quam. Etiam ultrices.' = 'API: python -m backend.app.collectors.cli ingest <dataset_id> · 일괄: powershell -File scripts/ingest_dropzone.ps1'
  'Source placeholders' = '참고자료'
  '[Author or organization]. [Source title]. [Publisher], [Year].' = 'LH-PREDICT. DATA_INGESTION_GUIDE.md. 2026-08-07.'
  '[Author or organization]. [Report or article title]. [Month Year].' = 'LH-PREDICT. config/data_sources.json. 2026-08-07.'
  '[Dataset owner]. [Dataset name and version]. Accessed [Month Year].' = '제공기관별 확보 원본 파일 및 승인 API. 적용 시 원본 버전과 수집시각 기록.'
  '[Interviewee or team]. [Interview or workshop notes]. [Date].' = '사용자 제공 데이터 목록 및 LH-PREDICT 필요데이터 획득 가이드 PDF. 2026-08-06.'
  'Template note. Replace bracketed placeholders, update the table of contents, and confirm page references before publishing.' = '문서 상태: 실제 데이터 투입 전 준비 보고서. API 응답·원본 파일 검증 결과에 따라 갱신 필요.'
}

$word = New-Object -ComObject Word.Application
$word.Visible = $false
try {
  $document = $word.Documents.Open($docx)
  foreach ($pair in $replacements.GetEnumerator()) {
    $find = $document.Content.Find
    $find.ClearFormatting()
    $find.Replacement.ClearFormatting()
    $find.Text = $pair.Key
    $find.Replacement.Text = $pair.Value
    [void]$find.Execute($pair.Key, $false, $false, $false, $false, $false, $true, 1, $false, $pair.Value, 2)
  }
  if ($document.Tables.Count -ge 2) {
    $table = $document.Tables.Item(2)
    $values = @(
      @('구분','관찰','운영 영향'),
      @('단지·시설','공식 코드가 핵심 연결키','코드 불일치는 수동검토'),
      @('시계열','관측·발표·예보시각 구분 필요','시간 누수와 잘못된 최신성 방지'),
      @('공간정보','CRS와 geometry 품질이 필수','잘못된 중첩·거리 계산 차단')
    )
    for ($row=1; $row -le [Math]::Min($table.Rows.Count,$values.Count); $row++) {
      for ($col=1; $col -le [Math]::Min($table.Columns.Count,$values[$row-1].Count); $col++) {
        $table.Cell($row,$col).Range.Text = $values[$row-1][$col-1]
      }
    }
  }
  $document.Save()
  $document.ExportAsFixedFormat($pdf, 17)
  $document.Close()
} finally {
  $word.Quit()
  [System.Runtime.InteropServices.Marshal]::ReleaseComObject($word) | Out-Null
}
Write-Host $docx
Write-Host $pdf
