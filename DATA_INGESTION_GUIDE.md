# LH-PREDICT 데이터 투입 가이드

기준일: 2026-08-07  
대상: 확보 완료된 API 및 파일데이터 15종

## 서울 회복력 분석 필수 상태

- 전국 LH Master는 `lh_complexes`에 유지하고 `scripts.build_seoul_resilience`가 서울 Profile만 파생합니다.
- `mois_flood_trace` 실제 SHP/GPKG/GeoJSON은 현재 미존재합니다. 파일이 투입되기 전 Flood ML 상태는 `BLOCKED_BY_DATA`이며 label이나 성능을 생성하지 않습니다.
- 현재 `seoul_flood_forecast_map` API 적재 2,094건에는 단계/ID만 있고 geometry가 없어 공간 중첩에 사용할 수 없습니다. 원본 공간파일이 필요합니다.
- 강우와 하수 수위는 기준시각을 보존하며 180분을 넘으면 `STALE`로 표시합니다. 오래된 값을 실시간으로 표시하지 않습니다.
- DEM NoData는 0m로 대체하지 않습니다. coverage가 없으면 해당 assessment는 `INSUFFICIENT`입니다.

### 행정안전부 침수흔적도 공간파일 투입

```powershell
.\.venv\Scripts\python.exe -m scripts.ingest_flood_trace "data/incoming/mois_flood_trace/승인파일.zip"
```

SHP, GeoPackage, GeoJSON, ZIP(SHP 1세트)을 지원합니다. 원본은 `raw`, 압축 해제본은 `staging`, 서울 영역 유효 geometry는 GeoParquet `processed`, 복구 불가 geometry 및 CRS 누락 metadata는 `quarantine`에 저장합니다. CRS를 추정하거나 강제로 덮어쓰지 않습니다. 실제 침수흔적 파일이 없으므로 현재 Geometry·Label·Flood ML은 모두 `BLOCKED_BY_DATA`입니다.

### DEM 공간 Feature 생성

```powershell
.\.venv\Scripts\python.exe -m scripts.build_terrain_features
.\.venv\Scripts\python.exe -m scripts.build_seoul_resilience
```

Raster별 실제 CRS와 NoData를 사용하며 100/300/500m 분석 결과를 `terrain_features`에 저장합니다.

## 바로 시작하기

1. `.env.example`을 `.env`로 복사하고 API URL과 키를 입력합니다.
2. 파일데이터를 아래 표의 `data/incoming/<dataset_id>/` 폴더에 넣습니다.
3. 단일 파일은 `python -m backend.app.collectors.cli ingest <dataset_id> --file <경로>`로 적재합니다.
4. 모든 드롭존 파일은 `powershell -File scripts/ingest_dropzone.ps1`로 일괄 적재합니다.
5. API 데이터는 `--file` 없이 같은 명령을 실행합니다.

원본은 실행별 `data/raw/<dataset_id>/<collection_run_id>/`에 복사되며 수정하지 않습니다. 정상 행은 `data/processed`, 실패 행은 `data/quarantine`에 Parquet으로 저장됩니다.

정상 행은 DB의 `source_records`에도 표준 JSON으로 적재됩니다. `lh_complexes` 정상 행은 운영 지도에서 바로 조회할 수 있도록 `complexes` 테이블에 함께 upsert됩니다.

## 데이터셋별 투입 위치

| dataset_id | 데이터 | 입력 | 파일/환경변수 |
|---|---|---|---|
| `lh_complexes` | 전국 LH 아파트 단지정보 | 파일/API | CSV·XLSX·JSON / `LH_COMPLEX_API_URL` |
| `molit_complex_list` | 공동주택 단지 목록 | API | `MOLIT_COMPLEX_LIST_API_URL` |
| `molit_complex_basic` | 공동주택 기본 정보 | API | `MOLIT_COMPLEX_BASIC_API_URL` |
| `kapt_maintenance_cost` | 공동주택 공용관리비 | API | `KAPT_MAINTENANCE_COST_API_URL` |
| `kma_vilage_forecast` | 기상청 단기예보 | API | `KMA_VILAGE_FORECAST_API_URL` |
| `kma_asos_hourly` | ASOS 시간자료 | API | `KMA_ASOS_HOURLY_API_URL` |
| `seoul_rainfall` | 서울시 강우량 | API | `SEOUL_RAINFALL_API_URL` |
| `seoul_sewer_level` | 서울시 하수관로 수위 | API | `SEOUL_SEWER_LEVEL_API_URL` |
| `mois_flood_trace` | 행정안전부 침수흔적도 | 파일/API | SHP·GPKG·GeoJSON·ZIP / `MOIS_FLOOD_TRACE_API_URL` |
| `seoul_flood_forecast_map` | 서울시 풍수해 침수예상도 | 파일 | SHP·GPKG·GeoJSON·ZIP |
| `ngii_dem` | 국토지리정보원 DEM | 파일 | TIF·TIFF·IMG·ZIP |
| `elevator_installations` | 승강기 설치 현황 20251231 | 파일 | CSV·XLSX |
| `elevator_building_coordinates` | 승강기 설치 건물 좌표 | 파일/API | CSV·XLSX·JSON / `ELEVATOR_BUILDING_COORD_API_URL` |
| `elevator_inspections` | 승강기 검사 결과 | 파일/API | CSV·XLSX·JSON / `ELEVATOR_INSPECTION_API_URL` |
| `elevator_corrective_actions` | 승강기 시정권고 내역 | 파일/API | CSV·XLSX·JSON / `ELEVATOR_CORRECTIVE_ACTION_API_URL` |

공공데이터포털 계열은 `DATA_GO_KR_SERVICE_KEY`, 기상청은 `KMA_SERVICE_KEY`를 사용합니다. 서울 데이터는 서비스별로 발급된 키가 다르므로 `SEOUL_RAINFALL_API_KEY`, `SEOUL_SEWER_LEVEL_API_KEY`, `SEOUL_FLOOD_FORECAST_MAP_API_KEY`를 각각 입력합니다.

## 파일 투입 예시

### 현재 배치된 승강기 설치현황

- `한국승강기안전공단_승강기 설치 현황_2015년 이전.csv`: 424,282행
- `한국승강기안전공단_승강기 설치 현황_2016년 이후.csv`: 461,368행
- 합계: 885,650행
- 위치: `data/incoming/elevator_installations/`
- 인코딩: UTF-8 BOM
- 필수 매핑: `승강기고유번호 → elevator_id`, `건물주소 → address`

원본·복사본 SHA-256 일치 여부를 확인했으며 상세 해시는 같은 폴더의 `manifest.json`에 기록했습니다.

```powershell
python -m backend.app.collectors.cli ingest lh_complexes `
  --file data/incoming/lh_complexes/LH_전국아파트단지정보.csv

python -m backend.app.collectors.cli ingest ngii_dem `
  --file data/incoming/ngii_dem/서울_DEM.tif

python -m backend.app.collectors.cli ingest elevator_installations `
  --file data/incoming/elevator_installations/승강기_설치현황_20251231.csv
```

현재 파일은 연도 구간별 2개이므로 각각 적재합니다.

```powershell
python -m backend.app.collectors.cli ingest elevator_installations `
  --file "data/incoming/elevator_installations/한국승강기안전공단_승강기 설치 현황_2015년 이전.csv"

python -m backend.app.collectors.cli ingest elevator_installations `
  --file "data/incoming/elevator_installations/한국승강기안전공단_승강기 설치 현황_2016년 이후.csv"
```

CSV는 UTF-8 BOM, CP949, EUC-KR 순으로 자동 판독합니다. Excel은 첫 번째 워크시트를 읽습니다. 여러 시트가 의미를 가지면 데이터셋별 어댑터를 추가해야 합니다.

## API 투입 예시

```powershell
python -m backend.app.collectors.cli ingest molit_complex_list
python -m backend.app.collectors.cli ingest kma_vilage_forecast
python -m backend.app.collectors.cli ingest seoul_rainfall
```

공통 API 수집기는 30초 timeout, 최대 4회 exponential backoff 재시도, 1,000건 단위 페이지네이션과 원본 응답 보존을 수행합니다. 실제 API가 경로 기반 페이지네이션, 별도 인증 헤더 또는 다른 파라미터명을 사용하면 해당 데이터셋 전용 어댑터가 필요합니다.

`.env`에는 공식 문서에서 확인한 공공데이터포털 GW, odcloud 및 서울 열린데이터광장 호출 URL이 입력되어 있습니다. 행정안전부 침수흔적도는 승인 후 실제 호출 URL이 제공되는 항목이므로 소개 페이지 URL을 API 값으로 잘못 입력하지 않고 비워 두었습니다.

서울 하수관로 수위의 `SEOUL_SEWER_START_TIME=auto-6h`, `SEOUL_SEWER_END_TIME=auto`는 실행 시점(Asia/Seoul) 기준 최근 6시간을 의미합니다. 과거 고정 구간을 조회하려면 두 값을 `YYYYMMDDHH` 형식으로 바꿉니다. `SEOUL_SEWER_DISTRICT_CODE=01`은 공식 명세 예시 구분코드이며 다른 구분을 조회할 때 해당 코드로 변경합니다.

## 표준 컬럼과 별칭

원본 컬럼은 `config/data_sources.json`의 `aliases`로 표준 컬럼에 연결됩니다. 예를 들어 `단지코드`, `단지 식별자`, `complex_id`는 모두 `complex_id`로 정규화할 수 있습니다.

실제 파일 컬럼명이 등록된 별칭과 다르면 수치를 추정하거나 위치 순서로 연결하지 말고 해당 JSON의 별칭 배열에 정확한 컬럼명을 추가합니다.

```json
"complex_id": ["complex_id", "단지코드", "실제_원본_컬럼명"]
```

## 기본 품질검사

- 데이터셋별 필수 표준 컬럼 존재 및 결측
- 위도 33~39, 경도 124~132 범위
- 단지·K-apt·승강기 식별자 중복
- 공간파일 geometry 존재
- DEM CRS 존재 및 래스터 크기·범위·NoData 메타데이터 기록
- 원본 SHA-256 데이터 버전
- 수집 실행별 전체·정상·격리 건수와 실패사유

검사 이력은 `data_collection_runs`, `data_quality_results`에 저장되고 다음 API로 확인할 수 있습니다.

```text
GET /api/v1/data-sources
GET /api/v1/data-quality
GET /api/v1/data-quality/{collection_run_id}
GET /api/v1/data-sources/{dataset_id}/records
```

## 데이터 연결 순서

1. 공식 LH 단지코드
2. K-apt 단지코드
3. 정규화 도로명주소
4. 단지명 + 시군구 + 주소
5. 검증 좌표 거리

현재 파이프라인은 원본 수집·표준화 준비까지 구현되어 있습니다. 3~5단계 자동 매칭과 `match_confidence`, `manual_review_required` 저장은 후속 구현 대상이며, 기준 이하 매칭을 자동 확정해서는 안 됩니다.

## 적용 전 확인사항

- API URL이 실제 승인된 운영 엔드포인트인지 확인
- API 응답 샘플 1페이지로 레코드 경로와 컬럼 별칭 확인
- 파일 인코딩, 좌표계, 측정 단위, 기준시각 확인
- 승강기번호와 건물 좌표의 연결 키 확인
- 침수 공간정보의 CRS와 침수일/침수심 속성 확인
- DEM 해상도·수직기준·NoData 값 확인
- 관리비의 부과년월, 금액 단위와 단지코드 확인
- 시정권고 데이터 이용범위와 개인정보·비공개 항목 확인

검증 실패 데이터는 수정해 정상 데이터로 위장하지 않습니다. 원인을 확인한 뒤 별도 정제 규칙을 코드와 문서에 남기고 다시 수집합니다.

## 서울 수문 7종 재수집 규약

원본은 `data/incoming/<dataset_id>/`에 두고 `incoming → raw → staging → processed → quarantine` 단계를 사용합니다. 공간 분석은 EPSG:5179, 지도 출력은 EPSG:4326을 사용합니다. 강우 시각은 Asia/Seoul로 해석한 뒤 UTC timezone-aware 값으로 저장합니다. 원본은 수정하지 않고 `source_file`, `data_version`, `processed_at`, `validation_status`를 보존합니다.

`python scripts/build_seoul_hydrology.py`는 침수흔적을 표준화·중복 제거하고 단지별 통합 Feature를 재생성합니다. 미확보 데이터셋은 수집 실행 기록에 `blocked_by_data`로 남습니다.

API 수집은 `python -m scripts.collect_seoul_hydrology_apis`를 사용합니다. 설정되지 않은 API는 `BLOCKED_BY_CONFIGURATION`, 인증·schema 오류는 `FAILED`, Geometry 없는 공간 속성 API는 적재 후 `PARTIAL_NO_GEOMETRY`로 구분합니다. 실패한 API 때문에 다른 API의 진단 결과가 사라지지 않습니다.
