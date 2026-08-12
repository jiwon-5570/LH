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
