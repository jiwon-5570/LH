# LH-PREDICT 구현 계획

## 초기 분석 (2026-08-06)

- 기존 구조: 단일 `app.py`, 단일 학습 스크립트, 모델링 스키마뿐인 시연 골격.
- 정상 기능: Streamlit UI 코드, NAVER Maps SDK 호출 코드, Claude 단일 프롬프트 코드, HistGradientBoosting 학습 골격.
- 현재 오류: 초기 환경에 pytest 미설치. 실제 데이터·DB·API·모델 산출물 없음.
- 재사용: 모델 feature 후보와 NAVER 지도 인증 방식.
- 삭제하면 안 되는 코드: 실제 데이터용 `train_models.py` feature 정의와 `data/modeling_table_schema.csv`.
- 제거 대상: 가상 단지, 합성 좌표·강우·위험확률, 이를 사용한 경보와 Claude 입력.
- 신규 대상: FastAPI/Pydantic, SQLAlchemy, 검증 수집기, 모델 배포 게이트, 운영 UI, Docker, 테스트.
- 실제 데이터 연동: 현재 0건. 승인된 파일/API 응답을 수집기에 투입해야 함.
- API 키 필요: NAVER_MAP_CLIENT_ID, DATA_GO_KR_SERVICE_KEY, KMA_SERVICE_KEY, SEOUL_RAINFALL_API_KEY, SEOUL_SEWER_LEVEL_API_KEY, SEOUL_FLOOD_FORECAST_MAP_API_KEY, ANTHROPIC_API_KEY.
- 기관 승인 필요: LH/K-apt 상세 API, 승강기 검사·시정권고 상세, 하수관로 수위, 내부 유지보수·고장 이력.

## 14일 일정

Day 1 구조·정직성 게이트, Day 2 DB/API, Day 3~6 실제 수집·매칭, Day 7~9 학습·검증·등록, Day 10~11 UI/GIS, Day 12 AI 도구, Day 13 보고서, Day 14 통합·보안·운영 문서.

현재 저장소는 Day 1~2 운영 골격과 15종 데이터 입력 준비를 구현했다. 외부 API 응답·실제 파일의 컬럼 및 단위 검증이 끝나지 않은 기능은 완료로 표시하지 않는다.

## 서울형 RESILIENCE 전환 계획 (2026-08-12)

| Phase | 상태 | 결과/차단 사유 |
|---|---|---|
| 1 Audit | 완료 | DB SHA-256 백업, 무결성 정상, 기존 8개 테스트 통과, 기존 Ruff 67건 기록 |
| 2 Seoul scope | 완료 | 서울 125개 Profile, 좌표 검증 72개, 주소만 확인 53개 |
| 3 Flood ground truth | BLOCKED_BY_DATA | 행정안전부 침수흔적도 실제 공간파일 없음 |
| 4 Feature pipeline | 부분 완료 | DEM point, 구별 강우·하수 스냅샷; 관측소 좌표·거리와 flood geometry 부족 |
| 5 Flood ML | BLOCKED_BY_DATA | ground truth 부재. 모델/성능을 생성하지 않음 |
| 6 Facility | Baseline 완료 | 실제 시정권고·설치 연결 사용. 시간순 ML은 NOT_READY |
| 7 Resilience | 완료(v1) | 버전형 Composite Index, Data Confidence, TOP factors |
| 8 Stress test | 완료(v1) | 강우·수위 변화만 허용, 실행 이력 저장 |
| 9 API/UI | 완료(v1) | 서울 API, 대시보드, NAVER 회복력 지도, 상세 Dialog |
| 10 Claude/report | 부분 완료 | 구조화 context와 HTML 진단보고서; PDF 미구현 |
| 11 QA | 완료(v1) | 신규 포함 11개 테스트, 전체 Ruff, Streamlit AppTest, API/DB 무결성 통과 |

## Ground Truth/DEM 강화 (2026-08-12)

- CI: Linux import 경로 수정 후 GitHub Actions 실검증 대상
- Ground Truth: SHP/GPKG/GeoJSON/ZIP 수용, CRS 누락 `REVIEW_REQUIRED`, invalid geometry 복구·감사 metadata 구현. 실제 파일은 아직 없음
- DEM: 4도엽을 한 번 열어 100/300/500m 표고·상대표고·경사·저지대·Coverage Feature 생성
- Grid: 실제 서울 경계 입력을 받는 100m EPSG:5179 Grid 구조 준비. 경계/침수흔적 미확보로 운영 Grid와 label은 미생성
- Flood ML: 실제 침수흔적·서울 경계·label 정책 미확보로 `BLOCKED_BY_DATA`
- Resilience: Historical Exposure 50점 대체 제거, 가용 구성요소 가중치 재정규화
- Stress Test: 휴리스틱 점수 제거, modified feature만 저장하고 `NOT_READY`

## Seoul hydrology integration status (2026-08-17)

- [x] Canonical 7-dataset registry and incoming folders
- [x] Flood trace canonical GeoParquet and deterministic deduplication
- [x] Rain-pump 500m/1km/2km proximity features
- [x] Compact `flood_spatial_features` DB table
- [x] Six FastAPI detail endpoints and Streamlit evidence tab
- [ ] Flood forecast, rain-gauge location, pump attributes, river levels: `BLOCKED_BY_DATA`
- [ ] Exact Seoul boundary, 100m grid, negative-sample policy, spatial ML split: `NOT_READY`

## Realtime / Scenario dashboard (2026-08-19)

- [x] 실시간/시나리오 모드 전환 UI
- [x] 입력 검증 및 서울 전체 단지 일괄 재계산 API
- [x] 정적 Feature 재사용, 동적 강우·하수·하천 Feature만 변경
- [x] 실시간 평가와 분리된 `stress_test_runs` 영속화
- [x] 시나리오 KPI, NAVER 지도 점수, 영향 TOP 5 연결
- [ ] 검증 Flood ML 확보 후 scenario inference로 승격
# Cascading Risk Engine v1

- [x] 기존 DB/processed Feature 가용성 감사
- [x] 결정론적 Evidence Graph와 데이터 부족 상태 구현
- [x] 실시간·StressTestRun 시나리오 분석 API 구현
- [x] 분석 실행·경로 DB 저장 구현
- [x] React 단지 상세 `연쇄영향` 탭 구현
- [x] Claude 입력에 계산 완료된 Cascade 구조만 포함
- [x] 부정 테스트: 전기·승강기 고장 Node 생성 금지
- [ ] 내부설비 위치 데이터 확보 후 세부 기능영향 검증(현재 범위 밖)
# AI 보고서 출시 단계 (2026-08-21)

- [x] 서울/자치구/단지 범위별 실제 DB 집계
- [x] 회복력 분포, 순위, 비교, 근거 요인, 연쇄영향, 권고 생성
- [x] 결측값 제외와 데이터 부족 상태 분리
- [x] 생성 payload 스냅샷 및 기준 시각 영속화
- [x] HTML/PDF 렌더링과 다운로드 API
- [x] Claude 근거 제한 프롬프트 및 실패 fallback
- [x] React 보고서 생성·결과 화면
- [x] 단위 테스트와 실제 운영 DB 3개 범위 검증
- [ ] Alembic 기반 운영 DB 마이그레이션 도입
- [ ] 외부 PDF 시각회귀 및 접근성 자동검사
