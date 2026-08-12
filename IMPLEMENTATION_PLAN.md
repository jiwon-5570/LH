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
