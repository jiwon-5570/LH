from __future__ import annotations

import json
import re
import uuid
from collections import Counter
from datetime import UTC, date, datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.db.base import (
    ComplexDataLink,
    FloodSpatialFeature,
    ReportArtifact,
    ResilienceReportSnapshot,
    SeoulComplexProfile,
    TerrainFeature,
)
from backend.app.services.cascading_risk_service import analyze_realtime_cascade
from backend.app.services.seoul_resilience_service import latest_assessments

REPORT_VERSION = "resilience-report-v1"
REPORT_TYPES = {
    "resilience": "종합 회복력 보고서",
    "climate": "기후재난 분석 보고서",
    "facility": "시설 취약성 보고서",
    "cascade": "복합재난 연쇄영향 보고서",
}
LIMITATIONS = [
    "본 보고서는 공공데이터 기반 운영 의사결정 지원자료입니다.",
    "Re:Safe Score는 실제 재난 발생확률이 아닙니다.",
    "시설 취약도는 실제 시설 고장확률이 아닙니다.",
    "Cascading Risk는 현재 확인된 데이터 간 증거관계를 이용한 운영용 영향경로 분석이며 실제 미래 사고 발생을 확정적으로 예측하지 않습니다.",
    "건물 내부 전기실·기계실 등 상세 설비 위치정보가 없는 경우 해당 시설에 대한 결과는 REVIEW_REQUIRED 수준으로 표시합니다.",
    "최종 안전조치는 현장점검 및 전문가 검토가 필요합니다.",
]


def _scores(db: Session, profiles: list[SeoulComplexProfile], kind: str) -> dict[str, float]:
    ids = {p.complex_id for p in profiles}
    out = {}
    for cid in ids:
        item = latest_assessments(db, cid).get(kind)
        if item and item.score is not None:
            out[cid] = float(item.score)
    return out


def _avg(values):
    return round(sum(values) / len(values), 2) if values else None


def _grade(score):
    return "취약" if score <= 39 else "주의" if score <= 59 else "보통" if score <= 74 else "양호"


def _factor_rows(assessment):
    rows = (assessment.explanation_snapshot or {}).get("top_factors", []) if assessment else []
    return [
        {
            "label": x.get("label") or x.get("factor"),
            "value": x.get("value"),
            "unit": x.get("unit"),
            "source": x.get("source"),
            "contribution": x.get("contribution_points"),
        }
        for x in rows
        if x.get("value") is not None or x.get("contribution_points") is not None
    ][:5]


def _recommendation_reason(text: str, cascade: dict, detail: dict) -> str:
    """Turn verified features into a plain-language selection reason without inventing capacity or risk."""
    assessments = detail.get("assessments") or {}
    drainage = (assessments.get("drainage_infrastructure_context") or {}).get("features") or {}
    climate = (assessments.get("dynamic_climate_stress") or {}).get("features") or {}
    facility = (assessments.get("facility_vulnerability") or {}).get("features") or {}
    nodes = {node.get("node_id"): node for node in cascade.get("nodes", [])}
    missing = [item for node in nodes.values() for item in node.get("missing_evidence", [])]

    if "배수" in text:
        distance = drainage.get("nearest_pump_distance_m")
        pump_count = drainage.get("pump_count_1km")
        capacity = drainage.get("capacity_status")
        parts = []
        if distance is not None:
            parts.append(f"최근접 빗물펌프장이 약 {distance:,.0f}m 떨어져 있습니다")
        if pump_count is not None:
            parts.append(f"1km 이내 확인된 펌프장은 {pump_count}개입니다")
        if capacity in {None, "NOT_PROVIDED"}:
            parts.append("펌프 용량·운영 속성이 확보되지 않았습니다")
        rain_reference = climate.get("rain_reference") or {}
        p95 = rain_reference.get("p95")
        if p95 is not None:
            parts.append(
                f"1시간 강우가 과거 관측 상위 5% 기준인 {p95:g}mm 수준에 접근할 때 배수 상태 확인이 필요합니다"
            )
        return ". ".join(parts) + ("." if parts else "배수 관련 활성 분석 근거가 있어 시설 상태 확인이 필요합니다.")

    if "승강기" in text:
        count = facility.get("elevator_count")
        score = (assessments.get("facility_vulnerability") or {}).get("score")
        if count is not None:
            return f"승강기 {count}대가 연결되어 있고 시설 취약성 지수는 {score if score is not None else '미분석'}점입니다. 이는 고장확률이 아니므로 침수 영향 가능 설비의 실제 상태를 확인해야 합니다."

    if "지하" in text or "전기" in text or "기계" in text:
        return "건물 내부 전기·기계설비 위치와 방수 상태 데이터가 없어 영향 여부를 계산할 수 없습니다. 침수 노출이 커질 경우를 대비해 위치와 차수 상태를 현장에서 확인해야 합니다."

    active = [
        node.get("label") for node in nodes.values() if node.get("status") in {"ACTIVE", "WATCH"} and node.get("label")
    ]
    if active:
        return f"현재 분석에서 {', '.join(active[:3])} 항목이 관찰 또는 주의 상태로 선별되어 이 조치를 권고했습니다."
    if missing:
        return (
            f"{', '.join(dict.fromkeys(missing[:3]))} 데이터가 없어 위험을 확정할 수 없으므로 우선 확인이 필요합니다."
        )
    return "현재 DB의 분석 결과와 점검 우선순위를 바탕으로 선택했습니다."


def build_report_payload(
    db: Session, report_type: str, scope_type: str, scope_value: str | None, reference_date: date | None = None
) -> dict:
    if report_type not in REPORT_TYPES:
        raise ValueError("지원하지 않는 보고서 유형")
    all_profiles = db.scalars(select(SeoulComplexProfile).order_by(SeoulComplexProfile.complex_name)).all()
    if scope_type == "seoul":
        profiles = all_profiles
        scope = {"type": "seoul", "label": "서울 전체"}
    elif scope_type == "district":
        if not scope_value:
            raise ValueError("자치구를 선택하세요")
        profiles = [p for p in all_profiles if p.district == scope_value]
        scope = {"type": "district", "label": scope_value}
    elif scope_type == "complex":
        profile = db.get(SeoulComplexProfile, scope_value or "")
        if not profile:
            raise LookupError("서울 분석 대상 단지가 아닙니다")
        profiles = [profile]
        scope = {
            "type": "complex",
            "label": profile.complex_name,
            "complex_id": profile.complex_id,
            "district": profile.district,
        }
    else:
        raise ValueError("지원하지 않는 분석 범위")
    if not profiles:
        raise LookupError("선택 범위에 단지가 없습니다")
    scores = _scores(db, profiles, "resilience")
    all_scores = _scores(db, all_profiles, "resilience")
    distribution = Counter(_grade(x) for x in scores.values())
    summary = {
        "total_complexes": len(profiles),
        "analysis_available": len(scores),
        "average_resilience": _avg(list(scores.values())),
        "vulnerable": distribution["취약"],
        "caution": distribution["주의"],
        "normal": distribution["보통"],
        "good": distribution["양호"],
        "insufficient": len(profiles) - len(scores),
    }
    ranking = []
    for p in sorted(profiles, key=lambda x: scores.get(x.complex_id, 999)):
        if p.complex_id in scores:
            ranking.append(
                {
                    "complex_id": p.complex_id,
                    "complex_name": p.complex_name,
                    "district": p.district,
                    "score": scores[p.complex_id],
                    "grade": _grade(scores[p.complex_id]),
                }
            )
    assessments = {}
    comparison = {}
    detail = {}
    cascade = {}
    factors = []
    if scope_type == "complex":
        p = profiles[0]
        assessments = latest_assessments(db, p.complex_id)
        district_profiles = [x for x in all_profiles if x.district == p.district]
        district_scores = _scores(db, district_profiles, "resilience")
        selected = scores.get(p.complex_id)
        ascending = sorted(all_scores.values())
        district_ascending = sorted(district_scores.values())
        comparison = {
            "selected": selected,
            "district_average": _avg(list(district_scores.values())),
            "seoul_average": _avg(list(all_scores.values())),
            "seoul_lower_rank": ascending.index(selected) + 1 if selected in ascending else None,
            "seoul_analyzed": len(ascending),
            "district_lower_rank": district_ascending.index(selected) + 1 if selected in district_ascending else None,
            "district_analyzed": len(district_ascending),
            "seoul_lower_percentile": round((ascending.index(selected) + 1) / len(ascending) * 100, 1)
            if selected in ascending and ascending
            else None,
        }
        flood = db.get(FloodSpatialFeature, p.complex_id)
        terrain = db.scalars(select(TerrainFeature).where(TerrainFeature.complex_id == p.complex_id)).first()
        link = db.get(ComplexDataLink, p.complex_id)
        detail = {
            "profile": {c.name: getattr(p, c.name) for c in p.__table__.columns},
            "assessments": {
                k: {
                    "score": v.score,
                    "grade": v.grade,
                    "method_type": v.method_type,
                    "method_version": v.method_version,
                    "features": v.feature_snapshot,
                    "data_quality_status": v.data_quality_status,
                }
                for k, v in assessments.items()
            },
            "flood": None if not flood else {c.name: getattr(flood, c.name) for c in flood.__table__.columns},
            "terrain": None if not terrain else {c.name: getattr(terrain, c.name) for c in terrain.__table__.columns},
            "facility": None if not link else {c.name: getattr(link, c.name) for c in link.__table__.columns},
        }
        cascade = analyze_realtime_cascade(db, p.complex_id, persist=False)
        factors = _factor_rows(assessments.get("resilience"))
    else:
        cascade_levels = []
        for p in profiles:
            cascade_levels.append(analyze_realtime_cascade(db, p.complex_id, persist=False)["cascade_level"])
        cascade = {
            "levels": dict(Counter(str(x) for x in cascade_levels)),
            "high_level_count": sum(x >= 3 for x in cascade_levels),
        }
    findings = []
    if summary["insufficient"]:
        findings.append(
            {
                "text": f"{summary['insufficient']}개 단지는 Re:Safe 산정 근거가 부족합니다.",
                "evidence": {"insufficient": summary["insufficient"]},
            }
        )
    if summary["vulnerable"]:
        findings.append(
            {
                "text": f"회복력 취약 등급 단지가 {summary['vulnerable']}개 확인됩니다.",
                "evidence": {"vulnerable": summary["vulnerable"]},
            }
        )
    if summary["average_resilience"] is not None:
        findings.append(
            {
                "text": (
                    f"분석 가능 {summary['analysis_available']}개 단지의 평균 Re:Safe 점수는 "
                    f"{summary['average_resilience']}점이며, 양호 {summary['good']}개·보통 {summary['normal']}개·"
                    f"주의 {summary['caution']}개·취약 {summary['vulnerable']}개로 분포합니다."
                ),
                "evidence": {"summary": summary},
            }
        )
    if ranking:
        lowest = ranking[0]
        findings.append(
            {
                "text": (
                    f"현재 범위에서 가장 낮은 Re:Safe 점수는 {lowest['complex_name']}의 "
                    f"{lowest['score']}점({lowest['grade']})입니다. 이는 상대적 점검 우선순위이며 재난 확률이 아닙니다."
                ),
                "evidence": lowest,
            }
        )
    if scope_type == "complex":
        findings += [
            {
                "text": f"주요 반영 요인: {x['label']} ({x['value'] if x['value'] is not None else x['contribution']})",
                "evidence": x,
            }
            for x in factors[:3]
        ]
    priorities = (cascade.get("priorities") or []) if scope_type == "complex" else []
    recommendations = [
        {
            "priority": i + 1,
            "text": x,
            "reason": _recommendation_reason(x, cascade, detail),
            "evidence": cascade.get("paths", []),
        }
        for i, x in enumerate(priorities)
    ]
    if not recommendations and summary["insufficient"]:
        recommendations = [
            {
                "priority": 1,
                "text": "미분석 단지의 좌표·동적 수문 근거를 우선 보강합니다.",
                "reason": "데이터 부족 단지 존재",
                "evidence": {"count": summary["insufficient"]},
            }
        ]
    if not recommendations and ranking:
        recommendations = [
            {
                "priority": 1,
                "text": f"Re:Safe 점수가 낮은 {ranking[0]['complex_name']}부터 세부 근거와 현장 상태를 확인합니다.",
                "reason": "현재 분석 범위의 Re:Safe 오름차순 1위",
                "evidence": ranking[0],
            },
            {
                "priority": 2,
                "text": "주의·취약 등급 단지는 최신 강우·수위·배수시설 상태를 재확인하고 점검 결과를 기록합니다.",
                "reason": f"주의 {summary['caution']}개, 취약 {summary['vulnerable']}개",
                "evidence": {"caution": summary["caution"], "vulnerable": summary["vulnerable"]},
            },
        ]
    used_sources = []
    names = {
        "terrain": "국토지리정보원 DEM",
        "flood": "서울시 침수·수문 공간정보",
        "facility": "한국승강기안전공단",
        "resilience": "LH 단지정보 및 RiskAssessment",
    }
    for key, name in names.items():
        if key == "resilience" or detail.get(key):
            used_sources.append({"name": name, "status": "AVAILABLE"})
    reference_times = [
        v.assessed_at for p in profiles for v in latest_assessments(db, p.complex_id).values() if v.assessed_at
    ]
    reference_time = max(reference_times) if reference_times else None
    payload = {
        "report_type": report_type,
        "report_type_label": REPORT_TYPES[report_type],
        "scope_type": scope_type,
        "scope": scope,
        "generated_at": datetime.now(UTC),
        "reference_time": reference_time,
        "reference_date": reference_date.isoformat() if reference_date else None,
        "freshness": "STALE"
        if reference_time and (datetime.now(UTC).replace(tzinfo=None) - reference_time.replace(tzinfo=None)).days > 1
        else "CURRENT",
        "summary": summary,
        "comparison": comparison,
        "distribution": {"grades": [{"grade": g, "count": distribution[g]} for g in ("취약", "주의", "보통", "양호")]},
        "ranking": ranking[:10],
        "findings": findings,
        "recommendations": recommendations,
        "cascade": cascade,
        "top_factors": factors,
        "detail": detail,
        "methodology": {
            "resilience": "composite_index / resilience-composite-v1",
            "cascade": "evidence_graph / cascade-v1",
            "ml_status": "운영 미사용 / 검증 미완료",
            "ai_role": "구조화된 결과의 자연어 설명 보조",
        },
        "data_sources": used_sources,
        "limitations": LIMITATIONS,
        "report_version": REPORT_VERSION,
    }
    payload["ai_explanation"] = _ai_explanation(payload)
    return json.loads(json.dumps(payload, ensure_ascii=False, default=str))


def _fallback_explanation(payload):
    s = payload["summary"]
    scope = payload["scope"]["label"]
    average = f"{s['average_resilience']}점" if s["average_resilience"] is not None else "데이터 부족"
    ranking = payload.get("ranking") or []
    lowest = ranking[0] if ranking else None
    comparison = payload.get("comparison") or {}
    factors = payload.get("top_factors") or []
    lines = [
        "[종합 판단]",
        (
            f"{scope}의 실제 운영 DB 기준 분석 대상은 {s['total_complexes']}개이며, Re:Safe 산정 가능 단지는 "
            f"{s['analysis_available']}개입니다. 평균은 {average}이고 취약 {s['vulnerable']}개, 주의 "
            f"{s['caution']}개, 보통 {s['normal']}개, 양호 {s['good']}개로 분포합니다."
        ),
        "",
        "[핵심 근거]",
    ]
    if lowest:
        lines.append(
            f"현재 범위에서 점검 우선순위가 가장 높은 단지는 {lowest['complex_name']}이며 "
            f"Re:Safe {lowest['score']}점({lowest['grade']})입니다."
        )
    if comparison.get("selected") is not None:
        lines.append(
            f"선택 단지는 {comparison['selected']}점, 같은 자치구 평균은 "
            f"{comparison.get('district_average', '데이터 부족')}점, 서울 평균은 "
            f"{comparison.get('seoul_average', '데이터 부족')}점입니다."
        )
    if factors:
        factor_text = ", ".join(
            f"{item['label']} {item['value'] if item['value'] is not None else item['contribution']}"
            f"{item.get('unit') or ''}"
            for item in factors[:3]
        )
        lines.append(f"주요 반영 요인은 {factor_text}입니다.")
    if s["insufficient"]:
        lines.append(f"{s['insufficient']}개 단지는 산정 근거가 부족하므로 값 대신 데이터 부족으로 관리합니다.")
    lines.extend(
        [
            "",
            "[우선 조치]",
            (
                "낮은 점수 단지부터 원천 데이터의 최신성을 확인하고, 활성 수문·침수·시설 근거가 있는 항목을 "
                "현장에서 우선 점검한 뒤 결과를 다시 평가해야 합니다."
            ),
            "",
            "[해석상 주의]",
            (
                "Re:Safe 점수는 실제 재난 발생확률이나 법정 안전진단 결과가 아닌 운영 의사결정용 복합지수입니다. "
                "AI는 DB와 분석 엔진이 계산한 결과를 설명할 뿐 새로운 점수·확률·시설 상태를 만들지 않습니다."
            ),
        ]
    )
    return "\n".join(lines)


def _ai_explanation(payload: dict) -> str:
    """Ask Claude to explain only verified aggregate facts; always has a deterministic fallback."""
    fallback = _fallback_explanation(payload)
    settings = get_settings()
    if not settings.anthropic_api_key:
        return fallback
    evidence = {
        "scope": payload["scope"],
        "summary": payload["summary"],
        "comparison": payload["comparison"],
        "top_factors": payload["top_factors"],
        "cascade": payload["cascade"],
        "findings": payload["findings"],
        "ranking": payload["ranking"],
        "recommendations": payload["recommendations"],
        "limitations": payload["limitations"],
    }
    try:
        from anthropic import Anthropic

        message = Anthropic(api_key=settings.anthropic_api_key).messages.create(
            model=settings.claude_model,
            max_tokens=1200,
            temperature=0,
            system=(
                "당신은 LH 재난안전 분석 해설자입니다. 제공된 JSON 수치만 사용하고, 없는 값은 "
                "'데이터 부족'이라고 쓰세요. 확률·인과관계를 새로 만들지 말고, 회복력 점수는 상대적 "
                "운영 선별지수임을 명시하세요. 한국어로 [종합 판단], [핵심 근거], [비교 해석], "
                "[우선 조치], [해석상 주의] 순서로 구체적으로 작성하세요. 수치와 단지명을 가능한 한 "
                "명시하되 JSON에 없는 내용은 만들지 마세요."
            ),
            messages=[{"role": "user", "content": json.dumps(evidence, ensure_ascii=False, default=str)}],
        )
        text = "".join(block.text for block in message.content if getattr(block, "type", "") == "text").strip()
        return text or fallback
    except Exception:  # noqa: BLE001 - the report must fall back on any provider/SDK failure
        return fallback


def _safe_name(value):
    return re.sub(r"[^0-9A-Za-z가-힣_-]+", "_", value).strip("_") or "report"


def render_report(payload: dict, report_id: str) -> tuple[Path, Path]:
    output = get_settings().report_output_dir
    output.mkdir(parents=True, exist_ok=True)
    env = Environment(
        loader=FileSystemLoader(Path(__file__).resolve().parents[1] / "templates"), autoescape=select_autoescape()
    )
    html = env.get_template("resilience_report.html").render(report=payload)
    html_path = output / f"{report_id}.html"
    html_path.write_text(html, encoding="utf-8")
    pdf_path = (
        output / f"LH_ReSafe_{_safe_name(payload['scope']['label'])}_{datetime.now(UTC).strftime('%Y%m%d_%H%M')}.pdf"
    )
    _render_pdf(payload, pdf_path)
    return html_path, pdf_path


def _render_pdf(payload: dict, path: Path):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    font = "Helvetica"
    font_path = Path("C:/Windows/Fonts/malgun.ttf")
    if font_path.exists():
        pdfmetrics.registerFont(TTFont("Malgun", str(font_path)))
        font = "Malgun"
    doc = SimpleDocTemplate(str(path), pagesize=A4, rightMargin=32, leftMargin=32, topMargin=35, bottomMargin=35)
    style = lambda size=10: __import__("reportlab.lib.styles", fromlist=["ParagraphStyle"]).ParagraphStyle(
        "x", fontName=font, fontSize=size, leading=size * 1.5
    )
    story = [
        Paragraph(f"LH-PREDICT {payload['report_type_label']}", style(18)),
        Paragraph(payload["scope"]["label"], style(13)),
        Spacer(1, 15),
    ]
    s = payload["summary"]
    data = [
        ["대상 단지", "분석 가능", "평균 Re:Safe", "데이터 부족"],
        [
            str(s["total_complexes"]),
            str(s["analysis_available"]),
            str(s["average_resilience"] or "미분석"),
            str(s["insufficient"]),
        ],
    ]
    table = Table(data, colWidths=[120] * 4)
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), font),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#082b4c")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                ("PADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    story += [table, Spacer(1, 15)]
    for title, items in (
        ("주요 발견사항", [x["text"] for x in payload["findings"]]),
        ("권고사항", [x["text"] for x in payload["recommendations"]]),
        ("분석 한계", payload["limitations"]),
    ):
        story.append(Paragraph(title, style(13)))
        story.extend(Paragraph(f"• {x}", style()) for x in items)
        story.append(Spacer(1, 10))
    doc.build(story)


def generate_report(
    db: Session, report_type: str, scope_type: str, scope_value: str | None, reference_date: date | None = None
) -> dict:
    payload = build_report_payload(db, report_type, scope_type, scope_value, reference_date)
    report_id = uuid.uuid4().hex
    html, pdf = render_report(payload, report_id)
    now = datetime.now(UTC)
    complex_id = scope_value if scope_type == "complex" else None
    title = f"AI {payload['report_type_label']} - {payload['scope']['label']}"
    db.add(
        ReportArtifact(
            report_id=report_id,
            report_type=report_type,
            complex_id=complex_id,
            title=title,
            file_path=str(html),
            created_at=now,
        )
    )
    db.add(
        ResilienceReportSnapshot(
            report_id=report_id,
            scope_type=scope_type,
            scope_value=scope_value,
            report_version=REPORT_VERSION,
            payload_snapshot=payload,
            reference_time=datetime.fromisoformat(payload["reference_time"]) if payload.get("reference_time") else None,
            pdf_path=str(pdf),
            created_at=now,
        )
    )
    db.commit()
    return {
        "report_id": report_id,
        **payload,
        "html_download_url": f"/api/v1/seoul/reports/{report_id}/download/html",
        "pdf_download_url": f"/api/v1/seoul/reports/{report_id}/download/pdf",
    }
