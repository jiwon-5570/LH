# 개발 기록

## 2026-08-12 — CI/Ground Truth/DEM 강화

- CI 문제 원인: GitHub Actions Ubuntu의 `pytest` 실행 파일에서 저장소 루트가 import path에 없어 `backend` 모듈 수집 5건 실패
- CI 수정: pytest `pythonpath=["."]`, Actions `python -m pytest`, `PYTHONPATH=.` 적용
- DEM Feature: 실제 Raster CRS 사용, NoData 제외, 4도엽 경계 결합, 100/300/500m 표고·상대표고·경사·저지대·Coverage를 `terrain_features`에 저장
- 침수흔적도: 실제 파일 미존재. SHP/GPKG/GeoJSON/ZIP 수용, CRS 누락 검토, geometry 복구·격리·서울 bbox 필터 파이프라인 구현
- Flood ML: 실제 Ground Truth와 서울 행정경계가 없어 `BLOCKED_BY_DATA`; 모델과 성능 미생성
- 회복력: Historical Exposure 미확보 시 임의 50점 제거, 가용 구성요소 weight 재정규화 및 누락목록 저장
- Stress Test: 강우 0.7/하수 0.3 휴리스틱 제거. Feature 변화만 저장하고 score는 `None`, 상태는 `NOT_READY`
- 테스트: DEM buffer/NoData/도엽경계, Grid, invalid geometry, weight 누락, Stress NOT_READY를 포함해 확대
- 남은 blocker: 행안부 침수흔적도 실제 공간파일, 서울 행정경계 polygon, 관측소·센서 좌표

## 2026-08-12 — LH-PREDICT RESILIENCE — SEOUL

- 작업: 수정 전 전체 감사, 서울 Master/Profile, 명시적 risk assessment, Data Confidence, Composite Resilience, TOP factors, Climate Stress Test, 서울 API·Streamlit·NAVER popup, Claude context·HTML 보고서 전환
- 수정 파일: `backend/app/db/base.py`, `backend/app/main.py`, `backend/app/api/v1/router.py`, `frontend/app.py`, `frontend/components/naver_map.py`, `run.ps1`, 문서 4종
- 신규 파일: `backend/app/api/v1/seoul.py`, `backend/app/schemas/seoul.py`, `backend/app/services/seoul_resilience_service.py`, `scripts/build_seoul_resilience.py`, config 2종, 신규 테스트
- DB 변경: 기존 테이블/전국 3,183개 보존. `seoul_complex_profiles` 125, `risk_assessments` 750, `stress_test_runs`, `model_versions`, `model_evaluations` 추가
- 데이터 변경: 서울 좌표 검증 72개, 주소만 확인 53개. DB 백업 `artifacts/backups/lh_predict_phase1_20260812.db` 생성 및 SHA-256 일치 확인
- 테스트: 수정 전 기존 8개 통과·Ruff 67건 실패를 기준선으로 기록. 정리 후 기존 8개 + 신규 3개 = 11개 통과, 저장소 전체 Ruff 통과, Streamlit AppTest 예외 0, API/DB 무결성 통과
- 남은 이슈: 행안부 침수흔적도 미존재로 Flood ML `BLOCKED_BY_DATA`; 풍수해 예상도 API에는 geometry 없음; 강우·하수 관측소 좌표 부재 및 데이터 stale; Facility ML `NOT_READY`; PDF 미구현

## 2026-08-08

- AI 모델 설정을 사용자 지정 모델 `claude-sonnet-5`로 통일
- 서울 하수관로 조회시간을 실행 시점 기준 최근 6시간 자동 계산으로 설정
- 서울 풍수해 침수예상도 공식 `floodingDs` API URL 반영

## 2026-08-07

- 서울 강우량·하수관로 수위·풍수해 침수예상도 인증키를 데이터셋별 환경변수 3개로 분리
- 공식 제공기관 문서 기준 API URL 11개를 `.env`와 `.env.example`에 반영
- odcloud의 `page/perPage/serviceKey`와 서울시 경로형 인증·페이지네이션 처리 추가
- 행정안전부 침수흔적도는 승인 후 호출 URL 발급 전이므로 실행 URL을 비워 둠
- 실제 실행용 `.env` 생성 및 데이터별 한글 주석 추가
- 승강기 설치현황 실제 CSV 2개를 `data/incoming/elevator_installations`에 배치
- 총 885,650행, UTF-8 BOM, 원본/복사본 SHA-256 일치 확인
- 실제 헤더의 `건물주소`, `승강기고유번호`, 설치·제조·유지관리·정격·검사 컬럼 별칭 반영
- 확보된 API·파일데이터 15종을 `config/data_sources.json`에 등록
- 데이터셋별 `data/incoming/<dataset_id>` 드롭존 생성
- CSV, Excel, JSON, XML API, 공간 벡터, DEM 입력 어댑터 추가
- retry, 페이지네이션, 원본 보존, SHA-256 버전, 표준 컬럼 별칭 처리 추가
- 필수값·좌표·식별자 중복 검증과 quarantine 분리 추가
- 수집 실행 및 품질검사 DB 모델/API 추가
- `DATA_INGESTION_GUIDE.md`와 일괄 적재 PowerShell 스크립트 추가
- 제한: 제공받은 실제 파일/API 응답 샘플을 아직 투입하지 않아 원본 컬럼 별칭과 레코드 경로의 최종 검증은 필요

## 2026-08-06

- 가상 운영 데이터와 합성 예측 경로 제거
- FastAPI, Pydantic 응답, SQLAlchemy 저장 구조 추가
- 검증된 모델만 로드하는 배포 게이트 추가
- 실제 CSV 단지 적재 및 quarantine 분리 추가
- Streamlit 무데이터/장애 상태 UI 추가
- Docker Compose, CI, 단위 테스트 추가
- 제한: 실제 공공데이터/API 키 및 기관 승인 미제공, 모델 미학습, AI/보고서 도구 미구현

## 2026-08-17 — Seoul flood and hydrology integration

- 실제 원본 탐색 후 침수흔적 5개 연도 파일을 통합하고 65개 중복을 제거했다.
- 빗물펌프장 최근접 거리와 500m/1km/2km 개수 Feature를 추가했다.
- 7개 데이터셋 가용성을 `flood_spatial_features`에 명시적으로 기록했다.
- 실제 원본이 없는 4종은 `BLOCKED_BY_DATA`로 유지했다.
- 상세 FastAPI 6개와 Streamlit 통합 수문 Feature 탭을 연결했다.
- Flood ML은 필수 검증 조건 미충족으로 학습하지 않았다.

## 2026-08-19 — Realtime and scenario dashboard modes

- 서울 전체 분석 가능 단지에 동일 사용자 시나리오를 적용하는 `scenario_service`를 추가했다.
- 강우 -50~+200%, 하수·하천 -50~+100% 범위를 검증한다.
- 실시간 Feature Snapshot을 복사하고 동적 Feature만 변경한 뒤 기후 취약성과 회복력을 재계산한다.
- 결과를 `USER_SCENARIO`, `composite_scenario`, `scenario-baseline-v1`으로 표시하고 기존 `risk_assessments`는 변경하지 않는다.
- React 대시보드에 입력 패널, 전후 KPI, 시나리오 지도, 영향 TOP 5를 연결했다.
# 2026-08-21 — Cascading Risk Engine v1

- 신규 외부 데이터 없이 Terrain, FloodSpatial, HistoricalFlood, RainPump, RiskAssessment, ComplexDataLink, StressTestRun을 결합하는 `evidence_graph/cascade-v1`을 구현했다.
- Node는 `ACTIVE/WATCH/INACTIVE/INSUFFICIENT/REVIEW_REQUIRED`만 사용하며 확률을 만들지 않는다.
- `CascadeAnalysisRun`, `CascadePath`에 입력·결과·경로·근거를 저장한다.
- 현재 운영 DB 125개 단지 분석 결과: Level 0 44개, Level 1 81개, Level 2~5 0개. 모든 단지에 하나 이상의 부족 근거가 있으며 이는 현재 동적 수문 기준정보 한계를 정직하게 반영한 결과다.
- 단지 상세에 연쇄경로, Node 근거, 부족 근거, 운영 점검 우선순위를 추가했다.
# 2026-08-21 — 다중 범위 AI 보고서

- `resilience_report_snapshots` 테이블로 생성 당시 payload, 범위, 버전, 기준 시각, PDF 경로를 보존했다.
- 서울 전체·자치구·개별 단지 보고서 서비스와 HTML/PDF 렌더러를 추가했다.
- Claude는 제공된 JSON 근거만 설명하도록 제한했으며 모든 공급자 오류에서 규칙 기반 설명으로 복구한다.
- React 화면에 보고서 유형/범위/기준일 선택, KPI, AI 해설, 발견사항, 권고, 순위, 출처, 한계를 연결했다.
- 테스트 결과: Ruff 통과, pytest 53개 통과, Vite 프로덕션 빌드 통과.
- 실제 DB 검증: 서울 125개(평균 81.84), 강남구 21개(평균 80.2), 강남4BL 1개(85.8) 보고서와 HTML/PDF 다운로드 확인.
