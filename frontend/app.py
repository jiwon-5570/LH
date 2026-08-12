import importlib
import os
import re

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv, set_key

load_dotenv()

from frontend.api_client import download, get, patch, post
from frontend.components import naver_map as naver_map_module

# Streamlit reruns the page in the same interpreter; reload map code after edits.
importlib.reload(naver_map_module)
render_naver_map = naver_map_module.render_naver_map

st.set_page_config(page_title="LH-PREDICT RESILIENCE — SEOUL", page_icon=":material/shield:", layout="wide", initial_sidebar_state="expanded")

st.markdown(
    """
<style>
:root { --navy:#061a38; --navy2:#0a2d58; --blue:#1768e5; --line:#e4e9f1; --muted:#718096; }
.stApp { background:#f4f7fb; color:#132238; }
[data-testid="stHeader"] { background:#061a38; height:0; }
[data-testid="stMain"] .block-container { padding:.65rem 1.25rem 1rem; max-width:none; }
[data-testid="stSidebar"] { background:linear-gradient(180deg,#061a38 0%,#082750 100%); border-right:1px solid rgba(255,255,255,.08); }
[data-testid="stSidebar"] .block-container { padding:1.35rem .85rem; }
[data-testid="stSidebar"] * { color:#eef5ff; }
[data-testid="stSidebar"] [role="radiogroup"] { gap:.28rem; }
[data-testid="stSidebar"] [role="radiogroup"] label { padding:.58rem .65rem; border-radius:8px; transition:.16s ease; }
[data-testid="stSidebar"] [role="radiogroup"] label:hover { background:rgba(255,255,255,.08); }
[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) { background:linear-gradient(90deg,#1768e5,#1d5bd0); box-shadow:0 7px 18px rgba(0,80,210,.28); }
[data-testid="stSidebar"] hr { border-color:rgba(255,255,255,.12); }
h1,h2,h3 { color:#132238; letter-spacing:-.025em; }
.brand-title { color:white;font-size:1.55rem;font-weight:800;letter-spacing:-.02em; }
.brand-sub { color:#9eb1c9;font-size:.74rem;margin-top:.15rem;margin-bottom:1.6rem; }
.topbar { background:#061a38; position:fixed; left:0; right:0; top:0; height:74px; z-index:-1; }
.page-heading { font-size:1.25rem;font-weight:800;margin:0;color:#152238; }
.page-sub { color:#7a8799;font-size:.78rem;margin-bottom:.35rem; }
.kpi-card { background:white;border:1px solid var(--line);border-radius:12px;padding:.7rem .9rem;min-height:84px;box-shadow:0 3px 12px rgba(30,55,90,.045);display:flex;gap:.7rem;align-items:center; }
.kpi-icon { width:40px;height:40px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:1.15rem;font-weight:800;flex:0 0 auto; }
.kpi-label { color:#415064;font-size:.82rem;font-weight:650; }
.kpi-value { color:#101828;font-size:1.42rem;font-weight:800;line-height:1.05;margin-top:.1rem; }
.kpi-unit { font-size:.8rem;font-weight:600;margin-left:.18rem; }
.kpi-foot { color:#8793a5;font-size:.65rem;margin-top:.15rem; }
.panel-title { font-size:.94rem;font-weight:800;color:#1b293d;margin-bottom:.28rem; }
.empty-panel { min-height:210px;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;color:#8793a5; }
.empty-icon { width:44px;height:44px;border-radius:12px;background:#edf3fc;color:#3977d4;display:flex;align-items:center;justify-content:center;font-size:1.25rem;margin-bottom:.65rem; }
.feed-item { border:1px solid #e7ebf1;border-radius:10px;padding:.78rem;margin-bottom:.55rem;background:#fff; }
.feed-type { color:#d83a34;font-size:.75rem;font-weight:750; }
.feed-name { color:#27364a;font-size:.8rem;font-weight:650;margin-top:.12rem; }
.feed-meta { color:#8793a5;font-size:.68rem;margin-top:.2rem; }
[class*="st-key-risk_card_"] button { min-height:57px;text-align:left;justify-content:flex-start;padding:.38rem .72rem;border:1px solid #e7ebf1;background:white;box-shadow:none;font-size:.72rem;line-height:1.08; }
[class*="st-key-risk_card_"] button:hover { border-color:#7aa9ef;background:#f8fbff;box-shadow:0 6px 16px rgba(23,104,229,.10);transform:translateY(-1px); }
div[data-testid="stVerticalBlockBorderWrapper"] { background:white;border-color:var(--line);border-radius:14px;box-shadow:0 3px 12px rgba(30,55,90,.04); }
div[data-testid="stMetric"] { background:white;border:1px solid var(--line);border-radius:12px;padding:14px; }
[data-testid="stDataFrame"] { border:1px solid #e7ebf1;border-radius:10px;overflow:hidden; }
.api-box { margin-top:1.7rem;padding:.85rem;border:1px solid rgba(86,199,113,.28);border-radius:10px;background:rgba(3,20,45,.3); }
.api-ok { color:#61d17b;font-weight:750;font-size:.82rem; }
.api-caption { color:#9eb1c9;font-size:.68rem;margin-top:.28rem; }
button[kind="primary"] { border-radius:8px; }
@media (max-width:900px) { [data-testid="stMain"] .block-container { padding:.8rem; } .kpi-card{min-height:94px;} }
</style>
""",
    unsafe_allow_html=True,
)

NAV_ITEMS = {
    "대시보드": ":material/dashboard:  서울 재난회복력 대시보드",
    "지도 보기": ":material/map:  서울 LH 회복력 지도",
    "AI 위험 감지 피드": ":material/warning:  AI 재난 위험 피드",
    "단지 관리": ":material/apartment:  단지 회복력 분석",
    "예측 분석": ":material/rainy:  기후재난 분석",
    "설비 관리": ":material/build:  시설 취약도",
    "AI 안전 관제": ":material/psychology:  AI 안전 관제",
    "AI 보고서": ":material/description:  AI 회복력 보고서",
    "데이터 관리": ":material/database:  데이터 관리",
    "시스템 설정": ":material/settings:  시스템 설정",
}

with st.sidebar:
    st.markdown('<div class="brand-title">LH-PREDICT</div><div class="brand-sub">RESILIENCE — SEOUL</div>', unsafe_allow_html=True)
    st.caption("메뉴")
    selected_menu = st.radio("메뉴", list(NAV_ITEMS.values()), label_visibility="collapsed", key="navigation")
    page = next(key for key, label in NAV_ITEMS.items() if label == selected_menu)
    st.caption("검색 및 필터")
    region = st.selectbox("지역", ["서울 전체"], label_visibility="collapsed", key="region_filter")
    search = st.text_input("단지 검색", placeholder="단지명 또는 주소", label_visibility="collapsed", key="complex_search")
    health, health_error = get("/health")
    api_ok = bool(health and health.get("status") == "ok")
    st.markdown(
        f'<div class="api-box"><div class="api-ok">● &nbsp;API {"정상" if api_ok else "연결 불가"}</div>'
        f'<div class="api-caption">{"모든 백엔드 서비스가 응답 중입니다." if api_ok else "백엔드 실행 상태를 확인하세요."}</div></div>',
        unsafe_allow_html=True,
    )

complexes, api_error = get("/api/v1/seoul/complexes?limit=1000")
complexes = complexes or []
seoul_high_risk, _ = get("/api/v1/seoul/high-risk?max_resilience=59&limit=100")
seoul_high_risk = seoul_high_risk or []
quality, _ = get("/api/v1/data-quality")
predictions, _ = get("/api/v1/predictions/high-risk")
predictions = predictions or []
alerts, _ = get("/api/v1/alerts")
alerts = alerts or []
models, _ = get("/api/v1/models")
model_items = (models or {}).get("items", [])
distribution_data, _ = get("/api/v1/predictions/distribution")

if search:
    keyword = search.casefold()
    complexes = [item for item in complexes if keyword in f"{item.get('complex_name','')} {item.get('address','')}".casefold()]

@st.dialog("단지 재난회복력 상세", width="large", icon=":material/fact_check:")
def show_resilience_detail(complex_id: str):
    detail, detail_error = get(f"/api/v1/seoul/complexes/{complex_id}")
    if detail_error or not detail:
        st.error(f"상세 분석을 불러오지 못했습니다: {detail_error}")
        return
    assessments = detail.get("assessments", {})
    resilience = assessments.get("resilience") or {}
    confidence = assessments.get("data_confidence") or {}
    st.subheader(detail["complex_name"])
    st.caption(f"{detail['address']} · {detail.get('validation_status')} · 기준시각 {resilience.get('assessed_at', '미분석')}")
    cols = st.columns(4)
    cols[0].metric("회복력", "데이터 부족" if resilience.get("score") is None else f"{resilience['score']:.1f}점")
    cols[1].metric("기후 취약성", "미분석" if not assessments.get("climate_vulnerability") else f"{assessments['climate_vulnerability']['score']:.1f}점")
    cols[2].metric("시설 취약성", "미분석" if not assessments.get("facility_vulnerability") or assessments['facility_vulnerability'].get('score') is None else f"{assessments['facility_vulnerability']['score']:.1f}점")
    cols[3].metric("데이터 신뢰도", "미분석" if confidence.get("score") is None else f"{confidence['score']:.1f}점")
    st.warning("회복력은 운영 의사결정 지원용 복합지수이며 실제 재난 발생확률이 아닙니다.")
    st.markdown("#### 왜 취약한가? — 근거 TOP 5")
    factors = (resilience.get("explanation") or {}).get("top_factors", [])
    if factors:
        st.dataframe(pd.DataFrame(factors), hide_index=True, width="stretch")
    else:
        st.info("계산 가능한 근거가 부족합니다.")
    tabs = st.tabs(["기후·DEM", "시설", "데이터 품질", "Climate stress test"])
    with tabs[0]: st.json({k: assessments.get(k) for k in ("flood_susceptibility", "dynamic_climate_stress", "climate_vulnerability")})
    with tabs[1]: st.json(assessments.get("facility_vulnerability") or {"status":"INSUFFICIENT"})
    with tabs[2]: st.json(confidence or {"status":"INSUFFICIENT"})
    with tabs[3]:
        with st.form(f"stress_{complex_id}"):
            rain_change = st.select_slider("강우 변화", options=[0, 10, 30, 50], value=30, format_func=lambda x:f"+{x}%")
            sewer_change = st.select_slider("하수 수위 변화", options=[0, 10, 20, 30], value=20, format_func=lambda x:f"+{x}%")
            submitted = st.form_submit_button("시나리오 실행", type="primary")
        if submitted:
            result, error = post("/api/v1/seoul/stress-test", {"complex_id":complex_id,"rain_change_pct":rain_change,"sewer_change_pct":sewer_change})
            if error: st.error(error)
            elif result.get("scenario_score") is None: st.warning("관측 또는 기초 분석 데이터가 부족해 시나리오를 계산하지 못했습니다.")
            else: st.metric("Scenario vulnerability index", f"{result['scenario_score']:.1f}점", f"{result['scenario_score']-result['base_score']:+.1f}점")

def kpi_card(column, icon, label, value, unit, foot, colors):
    bg, fg = colors
    with column:
        st.markdown(
            f'<div class="kpi-card"><div class="kpi-icon" style="background:{bg};color:{fg}">{icon}</div>'
            f'<div><div class="kpi-label">{label}</div><div class="kpi-value">{value}<span class="kpi-unit">{unit}</span></div>'
            f'<div class="kpi-foot">{foot}</div></div></div>', unsafe_allow_html=True,
        )

def empty_state(icon, title, caption, min_height=210):
    st.markdown(
        f'<div class="empty-panel" style="min-height:{min_height}px"><div class="empty-icon">{icon}</div>'
        f'<b>{title}</b><div style="font-size:.75rem;margin-top:.25rem">{caption}</div></div>', unsafe_allow_html=True,
    )

@st.dialog("위험 선별 상세 근거", width="large", icon=":material/fact_check:")
def show_risk_detail(prediction_id: str):
    detail, detail_error = get(f"/api/v1/predictions/{prediction_id}/detail")
    if detail_error or not detail:
        st.error(f"상세 근거를 불러오지 못했습니다: {detail_error}")
        return
    prediction = detail["prediction"]
    complex_item = detail.get("complex") or {}
    risk_label = "침수" if prediction.get("risk_type") == "flood" else "설비"
    st.subheader(complex_item.get("complex_name", prediction.get("complex_id")))
    st.caption(f"{complex_item.get('address', '주소 미확인')} · 결과 ID {prediction_id}")
    score = float(prediction.get("risk_probability", 0)) * 100
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("위험 유형", risk_label)
    m2.metric("운영 선별지수", f"{score:.1f}점")
    m3.metric("선별 등급", prediction.get("risk_level", "-"))
    m4.metric("조치", detail.get("decision", "점검 검토"))
    st.warning("이 값은 사고·고장 확률이 아니라 실제 데이터 기반의 현장 점검 우선순위입니다.")

    breakdown = pd.DataFrame(detail.get("score_breakdown", []))
    left, right = st.columns([1, 1.15], gap="medium")
    with left:
        st.markdown("#### 점수가 높아진 이유")
        if not breakdown.empty:
            chart = breakdown.set_index("label")[["points"]].rename(columns={"points": "기여점수"})
            st.bar_chart(chart, horizontal=True, height=255)
            st.dataframe(
                breakdown[["label", "points"]].rename(columns={"label": "요인", "points": "기여점수"}),
                hide_index=True, width="stretch",
            )
        st.caption(f"계산식: {detail.get('formula', '-')}")
    with right:
        st.markdown("#### 실제 근거 데이터")
        evidence = pd.DataFrame(detail.get("evidence", []))
        if not evidence.empty:
            evidence["측정값"] = evidence.apply(lambda row: "미확인" if pd.isna(row.get("value")) else f"{row.get('value')} {row.get('unit', '')}".strip(), axis=1)
            st.dataframe(
                evidence[["label", "측정값", "source"]].rename(columns={"label": "항목", "source": "출처"}),
                hide_index=True, width="stretch", height=285,
            )
        st.caption(f"계산시각: {prediction.get('prediction_time', '-')} · 모델 버전: {prediction.get('model_version', '-')}")

    st.markdown("#### AI 근거 설명")
    cache = st.session_state.setdefault("risk_ai_explanations", {})
    if prediction_id not in cache:
        with st.spinner("Claude가 위 근거 데이터만 사용해 설명을 작성하고 있습니다..."):
            ai_result, ai_error = post(f"/api/v1/predictions/{prediction_id}/ai-explanation", {})
        cache[prediction_id] = ai_result.get("answer") if ai_result else f"AI 설명을 생성하지 못했습니다: {ai_error}"
    st.info(cache[prediction_id], icon=":material/psychology:")
    with st.expander("해석 시 주의사항"):
        st.write(detail.get("limitation", "현장 확인과 담당자의 최종 판단이 필요합니다."))

if page == "대시보드":
    st.markdown('<div class="page-heading">서울 재난회복력 대시보드</div><div class="page-sub">서울 소재 LH 공동주택의 취약성, 회복력과 데이터 신뢰도를 실제 적재 데이터로 확인합니다.</div>', unsafe_allow_html=True)
    st.caption("회복력 점수는 실제 재난 발생확률이 아니며, 데이터 부족 단지를 저위험으로 간주하지 않습니다.")
    total_complexes = len(complexes)
    eligible_count = sum(item.get("analysis_eligible", False) for item in complexes)
    vulnerable_count = sum(item.get("resilience_score") is not None and item["resilience_score"] <= 39 for item in complexes)
    insufficient_count = sum(item.get("data_confidence") is None or item.get("data_confidence", 0) < 35 for item in complexes)
    cards = st.columns(4, gap="medium")
    kpi_card(cards[0], "▦", "서울 LH 단지", f"{total_complexes:,}", "개", "전국 Master에서 동적 추출", ("#e7f0ff", "#1768e5"))
    kpi_card(cards[1], "✓", "분석 대상", f"{eligible_count:,}", "개", "주소·좌표 품질 기준", ("#e5f7ef", "#168a5b"))
    kpi_card(cards[2], "!", "회복력 취약", f"{vulnerable_count:,}", "개", "회복력 39점 이하", ("#ffe9e8", "#e13b36"))
    kpi_card(cards[3], "?", "데이터 부족", f"{insufficient_count:,}", "개", "신뢰도 35점 미만", ("#eee7ff", "#7446df"))

    st.space(8)
    map_col, feed_col = st.columns([2.15, 1], gap="medium")
    with map_col, st.container(border=True, height=370):
        st.markdown('<div class="panel-title">서울 LH 재난회복력 지도</div>', unsafe_allow_html=True)
        render_naver_map(complexes, height=310)
    with feed_col, st.container(border=True, height=370):
        st.markdown('<div class="panel-title">점검 우선 단지</div>', unsafe_allow_html=True)
        if seoul_high_risk:
            for item in seoul_high_risk[:5]:
                score = item.get("resilience_score")
                label = (f":red[**회복력 {item.get('resilience_grade', '미분석')}**]  \n"
                         f"**{item.get('complex_name', item.get('complex_id'))}**  \n"
                         f"{('데이터 부족' if score is None else f'{score:.1f}점')} · 상세 근거 보기")
                if st.button(label, key=f"resilience_card_{item['complex_id']}", width="stretch"):
                    show_resilience_detail(item["complex_id"])
        else:
            empty_state("◎", "취약 단지가 없습니다", "분석 결과 또는 데이터 상태를 확인하세요.", 285)

    st.space(8)
    trend_col, dist_col, table_col = st.columns([1.05, .9, 1.15], gap="medium")
    with trend_col, st.container(border=True, height=235):
        st.markdown('<div class="panel-title">분석 상태</div>', unsafe_allow_html=True)
        status_counts = pd.Series([item.get("validation_status", "UNKNOWN") for item in complexes]).value_counts()
        st.bar_chart(status_counts, horizontal=True, height=165)
    with dist_col, st.container(border=True, height=235):
            st.markdown('<div class="panel-title">회복력 분포</div>', unsafe_allow_html=True)
            if complexes:
                order = ["취약", "주의", "보통", "양호", "데이터 부족"]
                colors = {"취약":"#e53935", "주의":"#fb8c00", "보통":"#f6c945", "양호":"#35b987", "데이터 부족":"#94a3b8"}
                counts = pd.Series([item.get("resilience_grade") or "데이터 부족" for item in complexes]).value_counts().to_dict()
                levels = [level for level in order if counts.get(level, 0) > 0]
                values = [counts[level] for level in levels]
                total = sum(values)
                legend_labels = [f"{level}  {count:,}개 ({count/total*100:.1f}%)" for level, count in zip(levels, values)]
                figure = go.Figure(go.Pie(
                    labels=legend_labels, values=values, hole=.62, sort=False,
                    marker={"colors":[colors.get(level, "#94a3b8") for level in levels], "line":{"color":"white", "width":1}},
                    textinfo="none", hovertemplate="%{label}<extra></extra>",
                    domain={"x":[0, .52], "y":[0, 1]},
                ))
                figure.add_annotation(x=.26, y=.5, text=f"서울<br><b>{total:,}개</b>", showarrow=False, font={"size":12, "color":"#26364a"})
                figure.update_layout(
                    height=175, margin={"l":0,"r":0,"t":0,"b":0}, showlegend=True,
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    legend={"x":.57,"y":.5,"xanchor":"left","yanchor":"middle","font":{"size":10,"color":"#526174"},"traceorder":"normal"},
                )
                st.plotly_chart(figure, width="stretch", config={"displayModeBar":False, "responsive":True})
            else:
                empty_state("◔", "분포 데이터 없음", "현재 유효한 예측 결과가 없습니다.", 155)
    with table_col, st.container(border=True, height=235):
            st.markdown('<div class="panel-title">회복력 취약 단지</div>', unsafe_allow_html=True)
            if seoul_high_risk:
                table = pd.DataFrame(seoul_high_risk[:8])[["complex_name", "district", "resilience_score", "data_confidence"]]
                table.columns = ["단지명", "자치구", "회복력", "신뢰도"]
                st.dataframe(table, hide_index=True, width="stretch", height=155)
            else:
                empty_state("▤", "고위험 단지 없음", "배포 모델 결과가 아직 없습니다.", 155)
elif page == "지도 보기":
    st.markdown('<div class="page-heading">서울 LH 회복력 지도</div><div class="page-sub">회복력은 취약(빨강)·주의(주황)·보통(노랑)·양호(초록), 데이터 부족은 회색으로 표시합니다.</div>', unsafe_allow_html=True)
    with st.container(border=True):
        render_naver_map(complexes)
elif page == "AI 위험 감지 피드":
    st.markdown('<div class="page-heading">위험 감지 피드</div><div class="page-sub">실데이터 기반 운영 선별 결과와 담당자 확인 상태입니다.</div>', unsafe_allow_html=True)
    st.warning("운영 선별지수이며 학습·검증된 ML 예측 확률이 아닙니다.")
    if predictions:
        names = {c.get("complex_id"): c.get("complex_name") for c in complexes}
        frame = pd.DataFrame(predictions)
        frame["단지명"] = frame["complex_id"].map(names).fillna(frame["complex_id"])
        frame["선별지수"] = (frame["risk_probability"] * 100).round(1)
        st.dataframe(frame[["단지명", "risk_type", "risk_level", "선별지수", "prediction_time", "model_version"]], hide_index=True, width="stretch", height=430)
        unacked = [a for a in alerts if not a.get("acknowledged")]
        st.subheader("미확인 경보")
        if unacked:
            selected_alert = st.selectbox("확인할 경보", unacked, format_func=lambda a: f"{a.get('severity')} · {a.get('message')}")
            if st.button("선택 경보 확인 처리", type="primary"):
                _, error = patch(f"/api/v1/alerts/{selected_alert['alert_id']}/acknowledge")
                if error: st.error(error)
                else: st.success("확인 처리했습니다."); st.rerun()
        else: st.success("미확인 경보가 없습니다.")
    else: empty_state("◎", "현재 선별 결과가 없습니다", "운영 선별 실행 후 자동으로 표시됩니다.", 420)
elif page == "단지 관리":
    st.markdown('<div class="page-heading">단지 관리</div><div class="page-sub">운영 DB에 적재된 실제 LH 단지 목록입니다.</div>', unsafe_allow_html=True)
    st.dataframe(pd.DataFrame(complexes), hide_index=True, width="stretch", height=420)
    if complexes:
        chosen = st.selectbox("단지 상세", complexes, format_func=lambda c: f"{c.get('complex_name')} · {c.get('address')}")
        link, link_error = get(f"/api/v1/complexes/{chosen['complex_id']}/data-link")
        if link_error: st.info("이 단지는 아직 좌표·승강기 연결 결과가 없습니다.")
        else:
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("연결 승강기", f"{link.get('elevator_count', 0):,}대")
            c2.metric("시정권고", f"{link.get('corrective_count', 0):,}건")
            c3.metric("위도", link.get("latitude") or "미연결")
            c4.metric("경도", link.get("longitude") or "미연결")
elif page == "예측 분석":
    st.markdown('<div class="page-heading">운영 위험 분석</div><div class="page-sub">실제 수집 데이터로 계산한 현장 점검 우선순위입니다.</div>', unsafe_allow_html=True)
    st.warning("현재 활성 결과는 ML 예측이 아닌 규칙 기반 운영 선별지수입니다. 사고·고장 결과 라벨이 확보되면 별도 ML 검증 절차가 필요합니다.")
    if model_items: st.dataframe(pd.DataFrame(model_items), hide_index=True, width="stretch")
    if predictions:
        frame = pd.DataFrame(predictions)
        frame["선별지수"] = (frame["risk_probability"] * 100).round(1)
        left, right = st.columns(2)
        with left: st.bar_chart(frame.groupby("risk_type")["선별지수"].mean(), height=300)
        with right: st.bar_chart(frame.groupby("risk_level").size().rename("건수"), height=300)
        st.dataframe(frame, hide_index=True, width="stretch", height=340)
    else: empty_state("↗", "분석 결과 없음", "운영 선별 배치 실행 상태를 확인하세요.", 380)
elif page == "설비 관리":
    st.markdown('<div class="page-heading">설비 관리</div><div class="page-sub">LH 단지와 연결된 승강기 설치·시정권고 현황입니다.</div>', unsafe_allow_html=True)
    links, links_error = get("/api/v1/complex-links?limit=1000")
    if links_error: st.error(links_error)
    elif links:
        frame = pd.DataFrame(links)
        m1, m2, m3 = st.columns(3)
        m1.metric("설비 연결 단지", f"{(frame['elevator_count'] > 0).sum():,}개")
        m2.metric("연결 승강기", f"{int(frame['elevator_count'].sum()):,}대")
        m3.metric("시정권고", f"{int(frame['corrective_count'].sum()):,}건")
        st.dataframe(frame, hide_index=True, width="stretch", height=560)
    else: empty_state("⚙", "연결 설비 없음", "단지-설비 연결 배치를 실행하세요.", 420)
elif page == "데이터 관리":
    st.markdown('<div class="page-heading">데이터 관리</div><div class="page-sub">수집 실행과 검증·격리 현황을 확인합니다.</div>', unsafe_allow_html=True)
    runs = (quality or {}).get("collection_runs", [])
    if runs: st.dataframe(pd.DataFrame(runs), hide_index=True, width="stretch", height=520)
    else: st.info("수집 실행 이력이 없습니다.")
    with st.expander("원본 품질 응답"): st.json(quality or {"status":"unavailable", "message":"API 연결 불가"})
elif page == "AI 안전 관제":
    st.markdown('<div class="page-heading">AI 안전 관제</div><div class="page-sub">Claude Sonnet이 현재 운영 DB 근거만 사용해 점검 우선순위를 설명합니다.</div>', unsafe_allow_html=True)
    selected = st.selectbox("분석 대상", [None] + complexes, format_func=lambda c: "전체 단지" if c is None else f"{c.get('complex_name')} · {c.get('address')}")
    if "chat_messages" not in st.session_state: st.session_state.chat_messages = []
    for message in st.session_state.chat_messages:
        with st.chat_message(message["role"]): st.write(message["content"])
    prompt = st.chat_input("예: 지금 가장 먼저 점검할 단지와 근거를 알려줘", submit_mode="disable")
    if prompt:
        st.session_state.chat_messages.append({"role":"user", "content":prompt})
        with st.chat_message("user"): st.write(prompt)
        with st.chat_message("assistant"):
            with st.spinner("운영 DB를 조회하고 있습니다..."):
                response, chat_error = post("/api/v1/ai/chat", {"question":prompt, "complex_id":selected.get("complex_id") if selected else None})
            answer = response.get("answer") if response else f"관제 응답 실패: {chat_error}"
            st.write(answer)
        st.session_state.chat_messages.append({"role":"assistant", "content":answer})
elif page == "AI 보고서":
    st.markdown('<div class="page-heading">안전 보고서</div><div class="page-sub">현재 운영 DB 스냅샷을 근거로 HTML 보고서를 생성합니다.</div>', unsafe_allow_html=True)
    target = st.selectbox("보고 대상", [None] + complexes, format_func=lambda c: "전국 종합" if c is None else c.get("complex_name"))
    if st.button("보고서 생성", type="primary"):
        created, report_error = post("/api/v1/reports", {"report_type":"comprehensive", "complex_id":target.get("complex_id") if target else None})
        if report_error: st.error(report_error)
        else: st.success("보고서를 생성했습니다."); st.session_state.latest_report = created
    latest = st.session_state.get("latest_report")
    if latest:
        content, mime, error = download(latest["download_url"])
        if error: st.error(error)
        else: st.download_button("최신 보고서 다운로드", content, file_name=f"LH-PREDICT-{latest['report_id']}.html", mime=mime, type="primary")
    report_rows, _ = get("/api/v1/reports")
    if report_rows: st.dataframe(pd.DataFrame(report_rows), hide_index=True, width="stretch", height=420)
elif page == "시스템 설정":
    st.markdown('<div class="page-heading">시스템 설정</div><div class="page-sub">외부 서비스 연결과 지도 환경을 관리합니다.</div>', unsafe_allow_html=True)
    with st.container(border=True):
        st.subheader("NAVER Maps 설정")
        existing_client_id = os.getenv("NAVER_MAP_CLIENT_ID", "").strip()
        existing_secret = os.getenv("NAVER_MAP_CLIENT_SECRET", "").strip()
        st.success("Client ID가 설정되어 있습니다.") if existing_client_id else st.warning("Client ID가 아직 설정되지 않았습니다.")
        st.success("인증키(Client Secret)가 설정되어 있습니다.") if existing_secret else st.warning("인증키(Client Secret)가 아직 설정되지 않았습니다.")
        with st.form("naver_map_settings"):
            client_id = st.text_input("NAVER Maps Client ID / Key ID", placeholder="기존 값 유지 시 비워두세요").strip()
            client_secret = st.text_input(
                "NAVER Maps 인증키 / Client Secret",
                type="password",
                placeholder="기존 값 유지 시 비워두세요",
                help="서버 API 전용으로 .env에 저장하며 브라우저 지도 코드에는 전달하지 않습니다.",
            ).strip()
            current_auth = os.getenv("NAVER_MAP_AUTH_PARAM", "ncpKeyId")
            auth_label = st.selectbox(
                "인증 방식",
                ["신규 Maps API (ncpKeyId)", "기존 Maps API (ncpClientId)"],
                index=0 if current_auth != "ncpClientId" else 1,
                help="최근 NAVER Cloud Maps Application은 ncpKeyId를 사용합니다. 기존 Client ID라면 ncpClientId를 선택하십시오.",
            )
            submitted = st.form_submit_button("Client ID 저장", type="primary")
        if submitted:
            effective_client_id = client_id or existing_client_id
            if not re.fullmatch(r"[A-Za-z0-9_-]{5,100}", effective_client_id): st.error("Client ID는 공백 없이 영문·숫자·_·-만 입력하십시오.")
            elif client_secret and not re.fullmatch(r"[^\s]{5,200}", client_secret): st.error("인증키에는 공백을 사용할 수 없습니다.")
            else:
                set_key(os.path.abspath(".env"), "NAVER_MAP_CLIENT_ID", effective_client_id, quote_mode="never")
                if client_secret:
                    set_key(os.path.abspath(".env"), "NAVER_MAP_CLIENT_SECRET", client_secret, quote_mode="never")
                auth_param = "ncpClientId" if "기존" in auth_label else "ncpKeyId"
                set_key(os.path.abspath(".env"), "NAVER_MAP_AUTH_PARAM", auth_param, quote_mode="never")
                os.environ["NAVER_MAP_CLIENT_ID"] = effective_client_id
                if client_secret:
                    os.environ["NAVER_MAP_CLIENT_SECRET"] = client_secret
                os.environ["NAVER_MAP_AUTH_PARAM"] = auth_param
                st.success(".env에 저장했습니다. 지도 보기 메뉴에서 확인하십시오.")
        st.caption("Web 서비스 URL: http://127.0.0.1:8501 · http://localhost:8501")
else:
    st.markdown(f'<div class="page-heading">{page}</div>', unsafe_allow_html=True)
    empty_state("◇", "기능 준비 중", "실데이터와 검증 모델이 준비되는 순서대로 활성화됩니다.", 480)

if api_error:
    st.error(f"Backend API 연결 실패: {api_error}", icon=":material/error:")
st.caption("의사결정 지원 정보입니다. 현장 확인과 담당자의 최종 판단이 필요합니다. 모든 수치는 출처·기준시각·모델 버전이 있는 경우에만 표시합니다.")
