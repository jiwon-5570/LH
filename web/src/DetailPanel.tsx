import { useEffect, useMemo, useState } from "react";
import { api, fmt, type Complex, type Detail } from "./api";
import { X, ShieldCheck, CloudRain, Building2, Database, BrainCircuit, AlertTriangle } from "lucide-react";

const tabs = ["종합 근거", "공식 침수이력", "배수 인프라", "시설", "데이터 품질", "통합 수문 Feature"];

export function DetailPanel({ complex, onClose }: { complex: Complex; onClose: () => void }) {
  const [detail, setDetail] = useState<Detail | null>(null);
  const [flood, setFlood] = useState<any>(null);
  const [aiText, setAiText] = useState("");
  const [aiState, setAiState] = useState<"loading" | "claude" | "fallback">("loading");
  const [tab, setTab] = useState(0);
  const [error, setError] = useState("");

  useEffect(() => {
    setError(""); setDetail(null); setFlood(null); setAiText(""); setAiState("loading"); setTab(0);
    Promise.all([
      api<Detail>(`/api/v1/seoul/complexes/${complex.complex_id}`),
      api<any>(`/api/v1/seoul/complexes/${complex.complex_id}/flood-features`)
    ]).then(([d, f]) => {
      setDetail(d); setFlood(f);
      const prompt = "이 단지의 취약요인을 확보된 DB 근거만 사용해 4~6문장으로 설명해 주세요. 점수가 실제 재난 확률이 아님을 밝히고, 자료가 부족한 항목은 부족하다고 명시하며, 우선 점검 조치 2가지를 포함하세요.";
      api<any>("/api/v1/ai/chat", { method: "POST", body: JSON.stringify({ question: prompt, complex_id: complex.complex_id }) })
        .then(result => { setAiText(result.answer); setAiState("claude"); })
        .catch(() => { setAiText(buildVerifiedNarrative(d, f)); setAiState("fallback"); });
    }).catch(e => setError(e.message));
  }, [complex.complex_id]);

  const assessments = detail?.assessments || {};
  const resilience = assessments.resilience || {};
  const climate = assessments.climate_vulnerability || {};
  const facility = assessments.facility_vulnerability || {};
  const confidence = assessments.data_confidence || {};
  const evidence = useMemo(() => buildEvidence(detail, flood), [detail, flood]);

  return <section className="detail-panel" id="detail-panel">
    <div className="detail-head"><div><span className="eyebrow">상세 근거</span><h2>{complex.complex_name}</h2><p>{complex.address}</p></div><button className="icon-button" onClick={onClose} aria-label="닫기"><X /></button></div>
    {error ? <div className="error-box">상세 데이터를 불러오지 못했습니다: {error}</div> : !detail ? <div className="loading-block">검증 근거를 불러오는 중입니다.</div> : <>
      <div className="detail-metrics">
        <Metric icon={<ShieldCheck/>} label="회복력" value={scoreText(resilience.score)} />
        <Metric icon={<CloudRain/>} label="기후 취약성" value={scoreText(climate.score)} />
        <Metric icon={<Building2/>} label="시설 취약성" value={scoreText(facility.score)} />
        <Metric icon={<Database/>} label="데이터 신뢰도" value={scoreText(confidence.score)} />
      </div>
      <div className="notice">운영 의사결정 지원용 복합지수이며 실제 재난 발생확률이나 법정 안전진단 결과가 아닙니다.</div>
      <section className="ai-explanation">
        <div className="ai-explanation-head"><BrainCircuit/><div><b>AI 취약요인 해설</b><span>{aiState === "claude" ? "Claude · 검증 데이터 기반" : aiState === "fallback" ? "검증 규칙 기반 대체 설명" : "근거 데이터를 분석하는 중"}</span></div></div>
        {aiState === "loading" ? <div className="ai-skeleton">AI가 침수·지형·배수·시설·데이터 품질 근거를 읽고 있습니다.</div> : <p>{aiText}</p>}
      </section>
      <div className="tabs">{tabs.map((x, i) => <button className={tab === i ? "active" : ""} onClick={() => setTab(i)} key={x}>{x}</button>)}</div>
      <div className="tab-body">
        {tab === 0 && <EvidenceList value={evidence} />}
        {tab === 1 && <ReadableEvidence value={assessments.historical_exposure} missing="단지 좌표 또는 공식 침수 중첩 분석 결과가 아직 없습니다." />}
        {tab === 2 && <ReadableEvidence value={assessments.drainage_infrastructure_context} missing="단지 좌표가 없어 주변 배수펌프장과 거리·용량을 계산할 수 없습니다." />}
        {tab === 3 && <ReadableEvidence value={facility} missing="이 단지와 연결된 승강기 검사·시정권고 근거가 충분하지 않습니다." />}
        {tab === 4 && <ReadableEvidence value={confidence} missing="데이터 품질 평가 결과가 아직 생성되지 않았습니다." />}
        {tab === 5 && <ReadableEvidence value={flood} missing="통합 수문 Feature가 아직 생성되지 않았습니다." />}
      </div>
    </>}
  </section>;
}

function scoreText(value: unknown) { return value == null ? "자료 부족" : fmt(Number(value)); }

function buildVerifiedNarrative(detail: Detail, flood: any) {
  const assessments = detail.assessments || {};
  const confidence = assessments.data_confidence?.score;
  const resilience = assessments.resilience?.score;
  const sentences: string[] = [];
  sentences.push(`${detail.complex_name}의 회복력은 ${resilience == null ? "자료 부족으로 확정할 수 없으며" : `${Number(resilience).toFixed(1)}점이며`}, 이 값은 재난 발생확률이 아닌 운영 우선순위 지수입니다.`);
  if (detail.latitude == null || detail.longitude == null) sentences.push("검증된 단지 좌표가 없어 DEM 고도, 침수흔적 중첩, 주변 하천·배수펌프장 거리 분석을 수행할 수 없습니다.");
  else if (flood?.historical_flood_overlap) sentences.push("공식 침수흔적 공간정보와 단지 위치가 중첩되어 과거 침수 노출을 우선 확인해야 합니다.");
  else sentences.push("현재 확보된 공식 침수흔적에서는 단지 위치의 직접 중첩이 확인되지 않았습니다.");
  if (confidence != null && Number(confidence) < 35) sentences.push(`데이터 신뢰도는 ${Number(confidence).toFixed(1)}점으로 낮아, 낮은 회복력 점수의 상당 부분이 데이터 부족에서 비롯됐을 수 있습니다.`);
  const pumpDistance = flood?.distance_to_nearest_pump_station_m;
  if (pumpDistance != null) sentences.push(`가장 가까운 배수펌프장은 약 ${Math.round(Number(pumpDistance))}m 거리에 있습니다.`);
  sentences.push("우선 조치로 단지 좌표와 시설 식별자를 현장대장으로 확인하고, 배수시설 및 승강기 검사 이력을 재점검하는 것이 필요합니다.");
  return sentences.join(" ");
}

function buildEvidence(detail: Detail | null, flood: any) {
  if (!detail) return [];
  const a = detail.assessments || {};
  const rows: { label: string; value: string; status: "ok" | "missing" }[] = [];
  const add = (label: string, value: unknown, missing: string) => rows.push({ label, value: value == null || value === "" ? missing : String(value), status: value == null || value === "" ? "missing" : "ok" });
  add("검증된 단지 좌표", detail.latitude != null && detail.longitude != null ? `${Number(detail.latitude).toFixed(6)}, ${Number(detail.longitude).toFixed(6)}` : null, "미확보 · 지오코딩 또는 현장대장 좌표 필요");
  add("기후재난 취약성", a.climate_vulnerability?.score != null ? `${Number(a.climate_vulnerability.score).toFixed(1)}점` : null, "미산정 · 좌표 기반 강우·수위 결합 필요");
  add("지형·배수 취약성", flood?.distance_to_nearest_pump_station_m != null ? `최근접 펌프장 ${Math.round(Number(flood.distance_to_nearest_pump_station_m))}m` : null, "미산정 · 좌표와 배수시설 공간결합 필요");
  add("시설 취약성", a.facility_vulnerability?.score != null ? `${Number(a.facility_vulnerability.score).toFixed(1)}점` : null, "미산정 · 승강기 식별자 및 검사이력 연결 필요");
  add("공식 침수흔적 근접 이력", flood?.historical_flood_overlap != null ? (flood.historical_flood_overlap ? "단지 위치와 중첩 확인" : "직접 중첩 없음") : null, "미산정 · 단지 좌표 필요");
  add("데이터 신뢰도", a.data_confidence?.score != null ? `${Number(a.data_confidence.score).toFixed(1)}점` : null, "품질 평가 미생성");
  return rows;
}

function Metric({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) { return <div className="mini-metric"><span>{icon}</span><div><small>{label}</small><strong>{value}</strong></div></div>; }
function EvidenceList({ value }: { value: {label:string;value:string;status:string}[] }) { return <div className="evidence-list">{value.map((x, i) => <div className={`evidence-${x.status}`} key={i}><b>{x.label}</b><span>{x.value}</span></div>)}</div>; }

function ReadableEvidence({ value, missing }: { value: any; missing: string }) {
  if (!value || !Object.keys(value).length) return <MissingReason text={missing}/>;
  return <div className="readable-evidence">{Object.entries(value).map(([key, item]) => <div key={key}><b>{humanize(key)}</b><span>{formatValue(item)}</span></div>)}</div>;
}

function MissingReason({text}:{text:string}) { return <div className="missing-reason"><AlertTriangle/><div><b>현재 계산할 수 없는 항목입니다.</b><span>{text}</span></div></div>; }
function humanize(key:string) { const labels:Record<string,string>={score:"점수",grade:"등급",method_type:"산정 방식",method_version:"산정 버전",data_quality_status:"데이터 품질 상태",assessed_at:"산정 시각",feature_snapshot:"사용 근거 데이터",explanation:"산정 설명"}; return labels[key]||key.replaceAll("_"," "); }
function formatValue(value:any):string { if(value == null || value === "") return "원천자료 없음"; if(typeof value === "boolean") return value?"예":"아니오"; if(typeof value === "object") return JSON.stringify(replaceEmpty(value),null,2); return String(value); }
function replaceEmpty(value:any):any { if(Array.isArray(value)) return value.length?value.map(replaceEmpty):["자료 없음"]; if(value && typeof value === "object") return Object.fromEntries(Object.entries(value).map(([k,v])=>[k,replaceEmpty(v)])); return value == null || value === "" ? "원천자료 없음" : value; }
