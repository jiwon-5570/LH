# LH-PREDICT RESILIENCE — SEOUL

## React 운영 UI

운영 화면은 Streamlit에서 **React + TypeScript + Vite**로 전환되었습니다. FastAPI, SQLite/PostgreSQL, GIS 처리 및 AI 파이프라인은 기존 Python 구현을 그대로 사용합니다.

```powershell
# FastAPI와 React 개발 서버를 한 번에 실행하고 브라우저를 엽니다.
.\run.cmd
```

- React 대시보드: `http://127.0.0.1:8501`
- FastAPI 문서: `http://127.0.0.1:8000/docs`
- React 소스: `web/src`
- 프로덕션 빌드: `cd web; npm.cmd run build`

상세 근거 보기는 브라우저 상태로 즉시 열리며, Streamlit처럼 전체 Python 스크립트를 다시 실행하지 않습니다. NAVER 지도에는 브라우저 공개용 Client ID만 전달되고 Client Secret 및 기타 API 키는 백엔드 `.env`에만 유지됩니다.

> 서울 소재 LH 공동주택의 기후·시설 취약성과 재난회복력을 실제 공공데이터로 설명하는 의사결정 지원 플랫폼

전국 3,183개 LH 단지는 Master로 보존하고, 주소 정규화와 좌표 검증을 통과한 서울 단지만 분석합니다. 현재 실제 서울 Master는 125개이며 좌표·DEM 검증 완료 72개, 주소 확인·좌표 미확보 53개입니다. 숫자는 코드에 고정하지 않고 Profile 빌드 결과로 계산됩니다.

**Resilience Score는 실제 재난 발생확률이 아닙니다. Facility Vulnerability는 실제 고장확률이 아닙니다. 검증된 ML probability, 규칙 Baseline, Composite Index를 DB·API·UI에서 구분합니다.**

이 저장소는 **실제 데이터만 운영 화면과 모델에 사용**합니다. 데이터나 검증된 모델이 없으면 수치를 만들지 않고 `데이터 미수집`, `설비 이력 미확보`, `모델 검증 미통과`, `현재 예측 불가`처럼 상태를 표시합니다.

## 1. 핵심 기능

- 전국 LH 단지 기본정보 및 GIS 지도
- 단지별 침수·승강기 설비 위험 조회 API
- 고위험 예측과 경보 확인 처리
- 수집 데이터 품질 및 출처·기준시각 추적
- 검증 완료 모델만 운영에 사용하는 배포 게이트
- NAVER Maps 기반 React 운영 대시보드
- 실제 단지 CSV 검증·적재 및 부적합 행 격리

## 2. 현재 구현 상태

| 영역 | 상태 | 설명 |
|---|---|---|
| FastAPI | 구현 | health, 단지, 예측, 경보, 데이터 품질, 모델 API |
| PostgreSQL/PostGIS | 기반 구현 | Docker Compose 제공. 개발 기본값은 SQLite |
| React + TypeScript + Vite | 구현 | 무데이터·API 장애 상태를 포함한 운영 화면 |
| NAVER Maps | 구현 | 검증 좌표만 전달하며 키 미설정 시 표 형태 fallback |
| 단지 CSV 수집 | 구현 | 필수 컬럼, 좌표 범위, 주소, ID 중복 검증 |
| 모델 학습 골격 | 구현 | 시간순 분할, ROC-AUC, PR-AUC, Brier Score 저장 |
| 모델 운영 승인 | 구현 | `validated=true`가 아닌 산출물 사용 차단 |
| 공공 API별 수집기 | 미구현 | API 키, 제공기관 명세 및 이용 승인이 필요 |
| AI 안전 관제 | 비활성 | 실제 조회 도구와 Claude 연결 미구현, API는 503 반환 |
| AI 보고서/PDF | 구현 | 서울·자치구·단지별 실제 DB 집계, 스냅샷, HTML/PDF, Claude 실패 fallback |
| 전체 DB 28개 테이블/Alembic | 미구현 | 현재 단지·예측·경보 핵심 모델만 구현 |
| 실제 모델 성능 | 없음 | 실제 학습 데이터와 외부검증 결과가 없음 |

### 서울형 전환 상태 (2026-08-12)

- `seoul_complex_profiles`: 125개. 전국 `complexes` 3,183개는 삭제·변경하지 않음
- `risk_assessments`: 정적 침수 Baseline, 동적 기후 스트레스, 기후·시설 취약성, 데이터 신뢰도, 회복력 Composite Index를 명시적 method/version과 함께 저장
- `stress_test_runs`: 강우·하수 수위 변화 시나리오 입력과 결과 이력 저장
- NAVER 지도: 서울 단지와 회복력 등급별 마커, 근거 팝업
- Claude: Backend가 제공한 구조화된 서울 분석결과만 설명
- Flood ML: `BLOCKED_BY_DATA` — 서울 침수흔적도 2020·2022·2023·2024·2025 적재 완료, 2021 시계열·정확한 서울 경계·음성표본 정책·시간분리 검증 미완료
- Facility ML: `NOT_READY` — 시간순 차기 검사 라벨 학습표와 외부검증 미완료; 규칙 Baseline만 사용

### DEM 공간 Feature v2

실제 NGII DEM 4개 도엽(EPSG:5179, 90m)을 파일별 CRS로 읽어 서울 좌표 검증 단지의 100m/300m/500m 주변 Feature를 `terrain_features`에 저장합니다. NoData(-9999), NaN, inf는 제외하며 도엽 경계에서는 여러 Raster의 유효 픽셀을 합칩니다.

```text
relative_elevation_R = 단지 표고 - R 반경 평균표고
lowland_index_R = clamp(-relative_elevation_R / (2 × R 반경 표고 표준편차), 0, 1) × 100
```

저지대 지수 100은 단지가 주변 평균보다 2 표준편차 이상 낮다는 뜻이며 침수확률이 아닙니다. 유효 픽셀 면적/원형 Buffer 면적으로 DEM Coverage를 계산하고 60% 미만이면 `INSUFFICIENT`로 처리합니다.

Resilience v3는 공식 침수흔적도와 단지 좌표의 최근접 거리, 점 교차 여부, 100/300/500m 겹침 면적비와 연도 이력을 Historical Exposure 근거로 사용합니다. 이 값은 침수확률이 아닌 운영 근접지수입니다. 누락 구성요소는 임의 50점으로 대체하지 않고 가용 구성요소 가중치를 재정규화합니다. Climate Stress Scenario는 Feature 변화만 저장하고 검증 Flood ML 전에는 `scenario_score=null`, `NOT_READY`입니다.

현재 구현 범위를 넘어선 기능을 완료한 것으로 간주하면 안 됩니다.

### 다중 범위 AI 보고서 (2026-08-21)

- 범위: 서울 전체, 자치구, 개별 단지
- 유형: 종합 회복력, 기후재난, 시설 취약성, 복합재난 연쇄영향
- API: `POST /api/v1/seoul/reports/generate`, `GET /api/v1/seoul/reports/{report_id}`
- 다운로드: 보고서별 HTML과 한글 PDF
- 재현성: 생성 당시 전체 payload와 기준 시각을 `resilience_report_snapshots`에 보존
- 결측 처리: 평균에서 제외하고 `insufficient`로 별도 집계하며 값을 임의 보간하지 않음
- AI 역할: 검증된 구조화 결과만 자연어로 설명하며, 키 미설정·호출 실패 시 동일 근거의 규칙 기반 해설 사용

보고서 화면은 `AI 보고서` 메뉴에서 보고서 유형과 분석 범위를 선택해 생성합니다. PDF 생성에는 `reportlab`이 필요하므로 의존성 변경 후 `pip install -r requirements.txt`를 다시 실행합니다.

## 3. 데이터 원칙

운영 DB, 화면, 보고서, AI 응답과 모델 학습에 가상 단지, 임의 좌표, 합성 강우량, 하드코딩된 위험확률 또는 테스트 fixture를 사용하지 않습니다.

데이터 흐름은 다음과 같습니다.

```text
data/raw         원본 응답·파일, 수정 금지
data/staging     인코딩 및 컬럼 정규화
data/processed   검증을 통과한 서비스·학습 데이터
data/quarantine  검증 실패 데이터
```

테스트 데이터는 `tests/fixtures/`에서만 사용하며 운영 환경과 모델 학습에 적재하지 않습니다. 통계적 대치가 필요하면 방법, 대상 컬럼, 사유와 원래 결측 건수를 별도로 기록해야 합니다.

## 4. 데이터 출처와 연동 조건

예정 출처:

- LH 임대주택 및 전국 LH 아파트 단지정보
- 국토교통부 공동주택/K-apt 기본정보와 관리비
- 기상청 실황·초단기예보·단기예보
- 서울시 강우량·침수흔적·침수예상·하수관로 수위
- 서울시 과거 강우량 2021~2024: 48개 관측소·192개 파일을 10분 시계열로 분할 적재하고 실증 1/3/24시간 분위값 생성

과거 강우량 ZIP 갱신 명령:

```powershell
.\.venv\Scripts\python.exe -m scripts.ingest_rainfall_history "C:\파일경로\서울시 강우량 데이터(2021~2024).zip"
```

과거자료는 실시간 API 데이터와 분리 저장되며, 양의 강우 관측 p50/p90/p95/p99/p99.9를 현재 강우의 상대적 이례성 기준으로 사용합니다. 이는 강우 또는 침수 발생확률이 아닙니다.
- 서울시 빗물펌프장 공간정보: 118개 위치 적재, 단지별 최근접 거리와 1/3/5km 시설 수 제공
- 행정안전부 침수흔적도, 국토지리정보원 DEM
- 한국승강기안전공단 설치·검사·시정권고 정보

API 키만으로 접근할 수 없는 기관 내부 유지보수·고장 이력은 별도 협의가 필요합니다. 공개 데이터만으로 실제 배관 고장확률을 검증할 수 없으므로 배관 예지보전 확률은 제공하지 않습니다.

## 5. 지역 지원 정책

- 전국: 실제로 적재된 LH 단지 위치와 기본정보
- 서울특별시: 강우·침수·하수 수위가 연계되고 모델이 검증된 단지만 위험 분석
- 수도권 일부: 데이터 확보 범위 내 위험 분석
- 기타 지역: 기본정보와 데이터 확보 상태

## 6. 시스템 구성

```text
React/NAVER Maps
        │ HTTP
        ▼
FastAPI ── SQLAlchemy ── PostgreSQL/PostGIS
   │                         ▲
   ├─ 검증된 모델            │
   ├─ AI 조회 도구(예정)      │
   └─ 보고서 서비스(예정)     │
                             │
공공 API/파일 → raw → staging → processed/quarantine
```

## 7. 프로젝트 구조

```text
backend/app/
  api/v1/       FastAPI 라우터
  collectors/   실데이터 수집·검증
  core/         환경설정
  db/           SQLAlchemy 모델과 세션
  schemas/      Pydantic 응답 모델
  services/     모델 운영 준비도 검사
frontend/
  app.py        레거시 Streamlit 포털(기본 실행에서 제외)
  api_client.py Backend API 클라이언트
  components/   NAVER 지도 등 UI 구성요소
data/           raw/staging/processed/quarantine
artifacts/      모델, 평가결과, 보고서
tests/          단위·통합·E2E 테스트 영역
```

## 8. 요구 환경

- Python 3.11 이상
- PostgreSQL 16 + PostGIS 3.4 또는 Docker
- NAVER Cloud Maps Client ID
- 선택 기능별 공공데이터 API 키
- Claude 기능 활성화 시 Anthropic API 키와 명시적 모델명

현재 개발 PC에 Python 또는 Docker가 없다면 아래 명령은 실행되지 않습니다. Microsoft Store의 `python.exe` 실행 별칭은 실제 Python 설치가 아닙니다.

## 9. 로컬 설치 및 실행

### 한 번에 실행하기(Windows PowerShell)

프로젝트 폴더에서 다음 명령 하나만 실행하면 가상환경과 의존성을 준비하고 FastAPI와 React를 함께 시작합니다.

```powershell
.\run.cmd
```

포털은 `http://127.0.0.1:8501`, API 문서는 `http://127.0.0.1:8000/docs`에서 확인할 수 있습니다. 종료할 때는 실행한 창에서 `Ctrl+C`를 누르십시오.

PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

터미널 1에서 API를 실행합니다.

```powershell
uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

터미널 2에서 포털을 실행합니다.

```powershell
$env:FRONTEND_API_URL="http://127.0.0.1:8000"
streamlit run app.py --server.headless true
```

- API 문서: `http://127.0.0.1:8000/docs`
- 운영 포털: `http://127.0.0.1:8501`

## 10. 환경변수

`.env.example`을 `.env`로 복사한 뒤 값을 설정합니다. 실제 키와 비밀번호는 커밋하지 않습니다.

| 변수 | 용도 | 필수 시점 |
|---|---|---|
| `APP_ENV` | 실행 환경 | 항상 |
| `DATABASE_URL` | SQLAlchemy DB 연결 | 항상 |
| `FRONTEND_API_URL` | 레거시 Streamlit의 Backend 주소 | 레거시 UI 사용 시 |
| `NAVER_MAP_CLIENT_ID` | NAVER Maps JavaScript API v3 | 지도 활성화 |
| `NAVER_MAP_CLIENT_SECRET` | NAVER Maps 서버 API 인증키(Client Secret) | 지오코딩 등 서버 API 사용 시 |
| `DATA_GO_KR_SERVICE_KEY` | 공공데이터포털 API | 해당 수집기 사용 |
| `KMA_SERVICE_KEY` | 기상청 API | 기상 수집 |
| `SEOUL_RAINFALL_API_KEY` | 서울시 강우량 전용 키 | 강우량 수집 |
| `SEOUL_SEWER_LEVEL_API_KEY` | 서울시 하수관로 전용 키 | 하수 수위 수집 |
| `SEOUL_FLOOD_FORECAST_MAP_API_KEY` | 풍수해 침수예상도 전용 키 | 공간정보 수집 |
| `MOIS_FLOOD_TRACE_API_KEY` | 재난안전데이터공유플랫폼 침수흔적도 전용 키 | `DSSP-IF-00117` 속성 수집 |
| `ANTHROPIC_API_KEY` | Claude API | AI 기능 활성화 |

행정안전부 침수흔적도 승인 키는 `.env`의 아래 항목에 따옴표 없이 입력합니다.

```dotenv
MOIS_FLOOD_TRACE_API_KEY=발급받은_인증키
MOIS_FLOOD_TRACE_API_URL=https://www.safetydata.go.kr/V2/api/DSSP-IF-00117
```

인증 확인과 전체 속성 수집 명령은 다음과 같습니다.

```powershell
.\scripts\diagnose_api_keys.ps1
.\.venv\Scripts\python.exe -m scripts.ingest_mois_flood_trace_api
```

실제 승인 API 응답에는 일련번호(`SN`), 침수수심(`FLDN_DOWA`)과 Web Mercator WKT 도형(`GEOM`)이 함께 제공됩니다. 수집 결과는 `data/processed/mois_flood_trace_api`에 원본 속성 Parquet으로 보존하고, 서울 시도코드와 공간 범위를 모두 검증한 도형만 EPSG:5179로 변환하여 `data/processed/seoul_flood_trace/seoul_flood_trace.parquet`에 기존 연도별 공간파일과 통합합니다. 중복은 연도+정확한 geometry hash로 제거하며 행 순서로 결합하지 않습니다.

```powershell
# API 전체 수집 + 서울 공간자료 통합
.\.venv\Scripts\python.exe -m scripts.ingest_mois_flood_trace_api

# 이미 수집한 최신 API 캐시로 통합만 재실행
.\.venv\Scripts\python.exe -m scripts.ingest_mois_flood_trace_api --skip-collect

# 파일자료 → MOIS API → 단지별 100/300/500m 근거 Feature 전체 재생성
.\.venv\Scripts\python.exe -m scripts.build_seoul_hydrology
```
| `CLAUDE_MODEL` | 사용할 Claude 모델명(현재 `claude-sonnet-5`) | AI 기능 활성화 |
| `BASIC_AUTH_USERNAME/PASSWORD` | 인증 연동용 | 운영 배포 |

## 11. 실제 단지 데이터 적재

확보된 15개 API·파일데이터의 데이터셋 ID, 투입 폴더, 환경변수와 실행 예시는 [`DATA_INGESTION_GUIDE.md`](DATA_INGESTION_GUIDE.md)를 참고하십시오.

승인된 원본 CSV를 `data/raw/`에 보관합니다. 필수 컬럼은 다음과 같습니다.

```text
complex_id,complex_name,address,latitude,longitude,
source_name,source_url,observed_at
```

적재 명령:

```powershell
python -m backend.app.collectors.csv_complex_collector data/raw/complexes.csv
```

수집기는 다음을 처리합니다.

- 필수 컬럼 확인
- 위도 33~39, 경도 124~132 범위 확인
- 주소 누락 확인
- 중복 단지 ID 격리
- 출처와 관측·수집 시각 저장
- 원본 파일 SHA-256 기반 데이터 버전 저장
- 수집 실행 ID 기록

검증 실패 행은 `data/quarantine/complexes_<run_id>.csv`로 분리됩니다.

전체 데이터 소스 목록 확인과 드롭존 일괄 적재:

```powershell
python -m backend.app.collectors.cli list
powershell -File scripts/prepare_dropzones.ps1
powershell -File scripts/ingest_dropzone.ps1
```

## 12. 모델 학습과 검증

`data/modeling_table_schema.csv`에 맞는 실제 통합 데이터를 준비합니다.

```powershell
python train_models.py `
  --input data/processed/modeling_table.csv `
  --output-dir artifacts/models
```

현재 학습기는 HistGradientBoosting 기반 침수·설비 이진분류 골격입니다. 결과 산출물에는 feature, target, 모델 버전, ROC-AUC, PR-AUC, Brier Score와 검증 상태가 저장됩니다.

산출물의 기본값은 `validated=false`입니다. 시간 분할 외에 단지 Group Split, 지역 외부검증, 최근 연도 holdout, calibration 검토와 승인 절차가 완료되기 전에는 운영 예측에 사용하지 않습니다.

## 13. API

| Method | Endpoint | 상태 |
|---|---|---|
| GET | `/health` | 구현 |
| GET | `/api/v1/complexes` | 구현 |
| GET | `/api/v1/complexes/{complex_id}` | 구현 |
| GET | `/api/v1/complexes/{complex_id}/flood-risk` | 구현 |
| GET | `/api/v1/complexes/{complex_id}/facility-risk` | 구현 |
| GET | `/api/v1/predictions/high-risk` | 구현 |
| GET | `/api/v1/alerts` | 구현 |
| PATCH | `/api/v1/alerts/{alert_id}/acknowledge` | 구현 |
| GET | `/api/v1/data-quality` | 구현 |
| GET | `/api/v1/data-sources` | 구현 |
| GET | `/api/v1/data-sources/{dataset_id}/records` | 구현 |
| GET | `/api/v1/data-quality/{collection_run_id}` | 구현 |
| GET | `/api/v1/models` | 제한 응답 |
| POST | `/api/v1/ai/chat` | 비활성, 503 |
| GET/DELETE | `/api/v1/ai/conversations/...` | 빈 목록/404 |
| POST/GET | `/api/v1/reports...` | 비활성, 503/404 |

서울 회복력 API:

```text
GET  /api/v1/seoul/complexes
GET  /api/v1/seoul/complexes/{complex_id}
GET  /api/v1/seoul/complexes/{complex_id}/resilience
GET  /api/v1/seoul/complexes/{complex_id}/climate
GET  /api/v1/seoul/complexes/{complex_id}/facility
GET  /api/v1/seoul/complexes/{complex_id}/explanations
GET  /api/v1/seoul/high-risk
POST /api/v1/seoul/stress-test
GET  /api/v1/models
GET  /api/v1/seoul/models/{model_id}/evaluation
```

서울 Profile과 assessment를 수동 갱신하려면 다음을 실행합니다. `run.cmd`도 시작 시 같은 작업을 수행합니다.

```powershell
.\.venv\Scripts\python.exe -m scripts.build_seoul_resilience
```

예측 데이터가 없으면 위험 API는 임의 확률 대신 HTTP 404와 `현재 예측 불가`를 반환합니다.

## 14. NAVER Maps

NAVER Cloud Console에서 Dynamic Map을 활성화하고 Web 서비스 URL에 로컬 및 배포 주소를 등록합니다.

```env
NAVER_MAP_CLIENT_ID=발급받은_Client_ID
```

인증 쿼리 파라미터는 `ncpKeyId`를 사용합니다. 키가 없거나 좌표가 검증되지 않은 단지는 지도 마커로 표시하지 않습니다.

## 15. AI 안전 관제

AI 안전 관제는 Claude Sonnet과 현재 운영 DB의 단지·설비·운영 선별 결과를 연결합니다.

- 허용 목록 기반 Backend 조회 도구
- 도구 입력 Pydantic 검증
- 자유 SQL, DB 수정, 임계값 변경 차단
- 실제 조회 결과의 출처·기준시각·모델 버전 전달
- prompt injection 방어 및 출력 검증
- Claude 장애 시 사실을 만들지 않는 fallback

Claude는 위험확률이나 경보 단계를 계산하지 않고, 검증된 시스템 결과를 설명하는 역할만 수행해야 합니다.

## 16. 보고서

전국 또는 단지별 현재 운영 DB 스냅샷을 HTML 보고서로 생성하고 다운로드할 수 있습니다. `operational-screening-v1`은 검증된 ML 확률이 아니라 실제 데이터 기반 운영 선별지수임을 보고서에 함께 표시합니다.

## 16-1. 경량 데이터 보존 정책

- 전체 검증 데이터: `data/processed/<dataset>/*.parquet`
- 장기 원본 레코드 아카이브: `data/archive/source_records/*.parquet`
- 아카이브 행 수·해시: `data/archive/source_records/manifest.json`
- 운영 SQLite: 데이터셋별 최신 표본 100건과 정제·연결·위험·경보 데이터

추가 수집 시 전체 프레임은 압축 Parquet으로 보존되고 SQLite에는 `SOURCE_RECORD_SAMPLE_LIMIT`만 적재됩니다. 운영 DB를 다시 압축하려면 서버를 중지하고 다음을 실행합니다.

```powershell
.\.venv\Scripts\python.exe scripts\compact_operational_db.py
```

감사 또는 마이그레이션 목적으로 아카이브를 DB에 복원할 수 있습니다.

```powershell
.\.venv\Scripts\python.exe scripts\restore_source_records.py --dataset seoul_rainfall
```

## 17. Docker 실행

```powershell
Copy-Item .env.example .env
docker compose build
docker compose up -d
docker compose ps
```

서비스 포트:

- PostgreSQL/PostGIS: 내부 `5432`
- FastAPI: `8000`
- React(Vite): `8501`

운영 배포 전 DB 기본 비밀번호를 반드시 변경하고 TLS와 reverse proxy 인증을 적용합니다.

## 18. 테스트와 품질 검사

```powershell
python -m compileall .
ruff check .
pytest
```

현재 테스트는 health API, 빈 DB 응답의 정직성, 모델 미배포·미검증 차단을 확인합니다. 실제 수집기 통합, PostGIS 공간 질의, 인증, AI 도구, 보고서와 E2E 테스트는 추가해야 합니다.

## 19. 장애 대응

- API/DB 장애: 해당 기능만 비활성화하고 오류 상태 표시
- 실데이터 미수집: 마지막 정상 데이터가 있을 때만 기준시각과 함께 사용
- 오래된 데이터: 실시간으로 표현하지 않고 갱신 지연 경고
- 모델 파일 누락·손상·미검증: 예측 차단
- NAVER Maps 실패: 검증 단지 표로 fallback
- Claude 실패: AI 응답 생성 중지, 예측 결과 자체는 유지
- PDF 실패: 향후 HTML fallback 제공

## 20. 보안 및 운영 주의사항

- `.env`, API 키, DB 비밀번호를 저장소와 로그에 남기지 않습니다.
- 운영 관리자 기능은 reverse proxy 또는 애플리케이션 인증을 적용해야 합니다.
- 사용자 입력과 HTML 출력은 검증·escape합니다.
- AI에 자유 SQL, DB 수정, 데이터 삭제, 모델·임계값 변경 권한을 부여하지 않습니다.
- 본 시스템은 의사결정 지원 도구이며, 경보 발령과 시설 운행 중지는 현장 확인 및 담당자의 최종 판단을 따라야 합니다.

초기 분석과 14일 계획은 `IMPLEMENTATION_PLAN.md`, 변경 이력과 제한사항은 `DEVELOPMENT_LOG.md`에서 확인할 수 있습니다.

## 서울 수문·침수 통합 현황

운영 Dataset ID는 `seoul_flood_trace`, `seoul_flood_forecast_geometry`, `seoul_rain_gauge_locations`, `seoul_rain_pump_stations`, `seoul_pump_station_attributes`, `seoul_river_levels`, `seoul_rainfall_historical`로 고정했습니다.

현재 실제 원본과 연결된 것은 침수흔적도(2020, 2022~2025), 빗물펌프장 공간정보, 과거 강우(2021~2024)입니다. 나머지 예상침수도, 강우계 위치, 펌프 속성, 하천수위는 저장소에서 실제 원본/API 캐시가 발견되지 않아 `BLOCKED_BY_DATA`입니다. 없는 값은 0이나 임의 좌표로 대체하지 않습니다.

```powershell
.\.venv\Scripts\python.exe scripts\build_seoul_hydrology.py
.\.venv\Scripts\python.exe scripts\build_seoul_resilience.py
```

대용량 원본·Geometry·시계열은 GeoParquet/Parquet에, 화면 조회용 단지 집계는 SQLite의 `flood_spatial_features`에 저장합니다. 침수흔적은 과거 발생 근거, 침수예상도는 취약 공간 Feature로 구분합니다. Flood ML은 정확한 서울 경계, 100m grid, 음성/비교 표본 정책, 공간 분리 검증이 갖춰지기 전까지 `BLOCKED_BY_DATA`입니다.

### 서울 수문 API 키 입력 및 수집

`.env`에서 아래 값을 채웁니다. 세 OpenAPI 데이터셋은 서로 다른 인증키를 사용할 수 있으며, 강우량계 위치정보는 공식 FILE 전용 데이터셋입니다.

```dotenv
SEOUL_FLOOD_FORECAST_MAP_API_KEY=
SEOUL_FLOOD_FORECAST_MAP_API_URL=http://openapi.seoul.go.kr:8088/{key}/json/floodingDs/{start}/{end}/

SEOUL_RAIN_GAUGE_LOCATION_FILE_URL=https://data.seoul.go.kr/dataList/OA-22824/F/1/datasetView.do

SEOUL_PUMP_STATION_ATTRIBUTE_API_KEY=
SEOUL_PUMP_STATION_ATTRIBUTE_API_URL=http://openapi.seoul.go.kr:8088/{key}/json/Drps/{start}/{end}/

SEOUL_RIVER_LEVEL_API_KEY=
SEOUL_RIVER_LEVEL_API_URL=http://openapi.seoul.go.kr:8088/{key}/json/ListRiverStageService/{start}/{end}/

HYDROLOGY_COLLECTION_MIN_INTERVAL_MINUTES=60
```

API URL은 서울 열린데이터광장 상세 페이지의 실제 서비스명을 사용한 `{key}/{start}/{end}` 템플릿입니다. 키 값만 따옴표 없이 입력합니다. 강우량계 위치 파일은 내려받은 뒤 `seoul_rain_gauge_locations` Dataset ID로 적재합니다. 이후 다음 명령 하나로 설정된 API만 수집하고 단지 Feature를 갱신합니다.

```powershell
.\.venv\Scripts\python.exe -m scripts.collect_seoul_hydrology_apis
```

최근 성공 파일이 설정 간격 이내면 재수집을 건너뛰어 디스크 증가와 API 호출을 줄입니다. 즉시 강제 갱신하려면 명령 끝에 `--force`를 붙입니다.

설정 및 적재 상태는 `GET /api/v1/seoul/hydrology-sources`에서 키 값을 노출하지 않고 확인할 수 있습니다. `floodingDs`는 실제 검증 결과 2,094개의 단계 속성을 반환하지만 Geometry는 반환하지 않으므로 `PARTIAL_NO_GEOMETRY`로 관리하며, 공간파일과 `space_id`로 결합되기 전에는 침수예상 면적비를 계산하지 않습니다.

## 실시간 모드와 시나리오 모드

- **실시간 모드**는 DB에 적재된 최신 공공데이터와 기존 `risk_assessments`만 표시합니다.
- **시나리오 모드**는 실제 단지·DEM·침수이력·배수시설·시설정보를 고정하고 사용자가 입력한 강우·하수관·하천 수위 변화율만 적용하는 Stress Test입니다.
- 입력은 `scenario_input=true`, `source=USER_SCENARIO`로 구분되어 `stress_test_runs`에 별도 저장되며 실시간 평가를 덮어쓰지 않습니다.
- 결과는 `scenario-baseline-v1` 복합 취약도 지수이며 실제 미래 재난 발생확률이나 기상예보가 아닙니다.

```http
POST /api/v1/seoul/scenarios/run
Content-Type: application/json

{"rain_change_pct":50,"sewer_change_pct":20,"river_change_pct":10,"apply_to_all_complexes":true}
```
# Cascading Risk Engine v1

LH-PREDICT의 Cascading Risk는 실제 재난 발생확률이 아니라 현재 확보된 공공데이터 간 조건관계를 이용한 **증거 기반 운영 영향경로 분석**이다. 강우, 하수·하천 수위, DEM 저지대, 공식 침수흔적, 침수예상도, 배수펌프장 접근성, 승강기 연계정보와 기존 검증 평가 스냅샷만 사용한다.

- 지원 환경 Node: `HEAVY_RAIN`, `SEWER_STRESS`, `RIVER_STRESS`, `LOWLAND_EXPOSURE`, `HISTORICAL_FLOOD_EXPOSURE`, `EXPECTED_FLOOD_EXPOSURE`, `DRAINAGE_LIMITATION`
- 복합·영향 Node: `COMPOUND_HYDROLOGIC_STRESS`, `FLOOD_EXPOSURE`, `ELEVATOR_SERVICE_IMPACT`, `UNDERGROUND_EQUIPMENT_REVIEW`, `ACCESS_FUNCTION_REVIEW`, `FUNCTIONAL_DISRUPTION`, `RESILIENCE_DEGRADATION`
- 단계: Level 0(미탐지)부터 Level 5(복수 기능영향 및 회복력 저하 점검 경로)까지이며 UI에서는 `운영용 연쇄영향 단계`로만 표시한다.
- Evidence: 활성 Node마다 데이터셋, Feature명, 실제 값과 부족한 근거를 함께 반환한다.
- 시나리오: `StressTestRun`의 기존값과 사용자 수정값을 각각 재평가하며 미래 예측으로 표현하지 않는다.
- 한계: 전기실·기계실·발전기실 등 내부설비 위치가 없으므로 고장·누전·정전·승강기 정지를 생성하지 않는다. 위치·방수상태 확인이 필요한 경우 `REVIEW_REQUIRED`, 기준정보가 없으면 `INSUFFICIENT`로 표시한다.

API는 `GET /api/v1/seoul/complexes/{complex_id}/cascade`, 재분석은 `POST .../cascade/analyze`, 시나리오 비교는 `GET /api/v1/seoul/stress-tests/{run_id}/cascade`를 사용한다. Re:Safe Score와 Cascade Level은 검증 전까지 별도 지표로 유지한다.
