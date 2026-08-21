import { useCallback, useEffect, useMemo, useState } from "react";
import {
  LayoutDashboard, Map, TriangleAlert, Building2, CloudRain, Wrench, BrainCircuit,
  FileText, Database, Settings, Search, Bell, RefreshCw, CheckCircle2, XCircle,
  ShieldCheck, ChevronRight, Send, Siren, Droplets, Activity, Radio, SlidersHorizontal
} from "lucide-react";
import { api, fmt, riskColor, type Complex, type Prediction } from "./api";
import { NaverMap } from "./NaverMap";
import { DetailPanel } from "./DetailPanel";

const menus = [
  ["대시보드", LayoutDashboard], ["지도 보기", Map], ["AI 재난 위험 피드", TriangleAlert],
  ["단지 회복력 분석", Building2], ["기후재난 분석", CloudRain], ["시설 취약도", Wrench],
  ["AI Chat", BrainCircuit], ["AI 보고서", FileText], ["데이터 관리", Database], ["시스템 설정", Settings]
] as const;

export default function App() {
  const [page, setPage] = useState("대시보드");
  const [complexes, setComplexes] = useState<Complex[]>([]);
  const [highRisk, setHighRisk] = useState<Complex[]>([]);
  const [predictions, setPredictions] = useState<Prediction[]>([]);
  const [quality, setQuality] = useState<any>(null);
  const [models, setModels] = useState<any>(null);
  const [hydrology, setHydrology] = useState<any>(null);
  const [health, setHealth] = useState(false);
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<Complex | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const [h, rows, risk, pred, q, m, hydro] = await Promise.all([
        api<any>("/health"), api<Complex[]>("/api/v1/seoul/complexes?limit=1000"),
        api<Complex[]>("/api/v1/seoul/high-risk?max_resilience=59&limit=100"),
        api<Prediction[]>("/api/v1/predictions/high-risk"), api<any>("/api/v1/data-quality"), api<any>("/api/v1/models"),
        api<any>("/api/v1/seoul/hydrology-sources")
      ]);
      setHealth(h.status === "ok"); setComplexes(rows); setHighRisk(risk); setPredictions(pred); setQuality(q); setModels(m); setHydrology(hydro);
    } catch (e: any) { setHealth(false); setError(e.message || String(e)); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);
  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return !q ? complexes : complexes.filter(x => `${x.complex_name} ${x.address}`.toLowerCase().includes(q));
  }, [complexes, search]);

  return <div className="app-shell">
    <aside className="sidebar">
      <div className="brand"><div className="brand-mark">LH</div><div><b>LH-PREDICT</b><span>AI 기반 주거단지 안전 관리 플랫폼</span></div></div>
      <nav>{menus.map(([label, Icon]) => <button key={label} className={page === label ? "active" : ""} onClick={() => { setPage(label); setSelected(null); }}><Icon size={19}/><span>{label}</span></button>)}</nav>
      <div className={`api-state ${health ? "ok" : "bad"}`}>{health ? <CheckCircle2/> : <XCircle/>}<div><b>API {health ? "정상" : "연결 불가"}</b><span>{health ? "백엔드와 DB가 응답 중입니다." : "백엔드 실행 상태를 확인하세요."}</span></div></div>
    </aside>
    <main>
      <header className="topbar"><div className="search"><Search/><input value={search} onChange={e => setSearch(e.target.value)} placeholder="단지명, 주소 검색"/></div><button className="icon-button" onClick={load} aria-label="새로고침"><RefreshCw className={loading ? "spin" : ""}/></button><Bell/><div className="admin"><b>관리자</b><span>시스템 관리자</span></div></header>
      <div className="content">
        {error && <div className="error-box">API 연결 오류: {error}</div>}
        {page === "대시보드" && <Dashboard rows={filtered} highRisk={highRisk} onSelect={setSelected} />}
        {page === "지도 보기" && <Page title="서울 LH 회복력 지도" subtitle="검증된 단지 좌표와 회복력 등급을 NAVER 지도에서 확인합니다."><div className="panel tall"><NaverMap rows={filtered} onSelect={setSelected}/></div></Page>}
        {page === "AI 재난 위험 피드" && <RiskFeed predictions={predictions} complexes={filtered} onSelect={setSelected}/>}
        {page === "단지 회복력 분석" && <ComplexList rows={filtered} onSelect={setSelected}/>}
        {page === "기후재난 분석" && <ComplexAnalysis rows={filtered} title="기후재난 분석" onSelect={setSelected}/>}
        {page === "시설 취약도" && <ComplexAnalysis rows={filtered} title="시설 취약도" onSelect={setSelected}/>}
        {page === "AI Chat" && <AiChat complexes={complexes}/>}
        {page === "AI 보고서" && <Reports complexes={complexes}/>}
        {page === "데이터 관리" && <DataManagement quality={quality} hydrology={hydrology}/>}
        {page === "시스템 설정" && <SystemSettings models={models}/>}
        {selected && <DetailPanel complex={selected} onClose={() => setSelected(null)}/>}
      </div>
    </main>
  </div>;
}

function Page({ title, subtitle, actions, children }: { title: string; subtitle: string; actions?: React.ReactNode; children: React.ReactNode }) { return <><div className="page-title"><div><h1>{title}</h1><p>{subtitle}</p></div>{actions}</div>{children}</>; }

function Dashboard({ rows, highRisk, onSelect }: { rows: Complex[]; highRisk: Complex[]; onSelect: (x: Complex) => void }) {
  type KpiKey = "all" | "eligible" | "vulnerable" | "insufficient";
  const [activeKpi, setActiveKpi] = useState<KpiKey | null>(null);
  const [mode, setMode] = useState<"realtime" | "scenario">(()=>sessionStorage.getItem("dashboard_mode")==="scenario"?"scenario":"realtime");
  const [scenarioInput, setScenarioInput] = useState({scenario_name:"",rain_change_pct:0,sewer_change_pct:0,river_change_pct:0});
  const [scenario, setScenario] = useState<any>(null);
  const [scenarioBusy, setScenarioBusy] = useState(false);
  const [scenarioError, setScenarioError] = useState("");
  const eligible = rows.filter(x => x.analysis_eligible).length;
  const vulnerable = rows.filter(x => x.resilience_score != null && x.resilience_score <= 39).length;
  const insufficient = rows.filter(x => x.data_confidence == null || x.data_confidence < 35).length;
  const kpiDetails: Record<KpiKey, { title: string; description: string; rows: Complex[] }> = {
    all: { title: "전체 LH 단지", description: "현재 운영 DB에서 검증된 서울 LH 단지 전체입니다.", rows },
    eligible: { title: "분석 가능 단지", description: "좌표와 핵심 근거 데이터가 확보되어 회복력 분석이 가능한 단지입니다.", rows: rows.filter(x => x.analysis_eligible) },
    vulnerable: { title: "회복력 취약 단지", description: "운영 회복력 지수가 39점 이하로 우선 확인이 필요한 단지입니다.", rows: rows.filter(x => x.resilience_score != null && x.resilience_score <= 39) },
    insufficient: { title: "데이터 보강 필요", description: "데이터 신뢰도가 35점 미만이거나 아직 계산되지 않은 단지입니다.", rows: rows.filter(x => x.data_confidence == null || x.data_confidence < 35) },
  };
  const selectedKpi = activeKpi ? kpiDetails[activeKpi] : null;
  const changeMode = (next:"realtime"|"scenario") => { setMode(next); sessionStorage.setItem("dashboard_mode",next); if(next==="realtime") sessionStorage.removeItem("active_scenario_id"); };
  const runScenario = async () => { setScenarioBusy(true); setScenarioError(""); try { const result=await api<any>("/api/v1/seoul/scenarios/run",{method:"POST",body:JSON.stringify({...scenarioInput,apply_to_all_complexes:true,created_by:"dashboard-user"})}); setScenario(result); sessionStorage.setItem("active_scenario_id",result.scenario_id); } catch(e:any) { setScenarioError(e.message||String(e)); } finally { setScenarioBusy(false); } };
  const scenarioById = new globalThis.Map<string,any>((scenario?.complex_results||[]).map((x:any)=>[x.complex_id,x]));
  const displayRows = mode === "scenario" && scenario ? rows.map(x=>{const s=scenarioById.get(x.complex_id);return s?{...x,resilience_score:s.scenario_resilience_score,resilience_grade:s.scenario_grade}:x}) : rows;
  const impactRows = scenario ? [...scenario.complex_results].filter((x:any)=>x.resilience_delta!=null).sort((a:any,b:any)=>a.resilience_delta-b.resilience_delta).slice(0,5) : [];
  const latestAssessedAt = rows.map(x=>x.assessed_at).filter(Boolean).sort().at(-1);
  const modeSwitch = <div className="dashboard-mode-wrap"><div className="dashboard-mode" role="group" aria-label="대시보드 분석 모드"><button type="button" className={mode === "realtime" ? "active" : ""} onClick={() => changeMode("realtime")} aria-pressed={mode === "realtime"}><Radio/>실시간 모드</button><button type="button" className={mode === "scenario" ? "active" : ""} onClick={() => changeMode("scenario")} aria-pressed={mode === "scenario"}><SlidersHorizontal/>시나리오 모드</button></div><small>{mode === "realtime" ? `현재 수집된 최신 공공데이터 기준${latestAssessedAt?` · 최종 평가 ${new Date(latestAssessedAt).toLocaleString("ko-KR")}`:" · 기준시각 없음"}` : "사용자 설정 조건의 Stress Test이며 실제 미래 예측값이 아닙니다."}</small></div>;
  return <Page title="통합 안전 관리 대시보드" subtitle="서울 LH 단지의 재난·설비 위험과 데이터 품질을 한눈에 확인합니다." actions={modeSwitch}>
    {mode === "scenario" && <section className="scenario-panel"><div className="scenario-panel-head"><div><b>시나리오 설정</b><span>STATIC DATA + USER SCENARIO VARIABLES</span></div><div className="scenario-presets">{[["현재 상태",0,0,0],["집중호우",30,15,10],["극한호우",80,35,25],["배수부담 증가",10,50,10],["복합 위험",50,30,30]].map(([n,r,s,v]:any)=><button key={n} onClick={()=>setScenarioInput({scenario_name:n,rain_change_pct:r,sewer_change_pct:s,river_change_pct:v})}>{n}</button>)}</div></div><div className="scenario-fields"><label>시나리오 이름<input value={scenarioInput.scenario_name} onChange={e=>setScenarioInput({...scenarioInput,scenario_name:e.target.value})} placeholder="자동 생성"/></label><label>강우 변화율 <b>{scenarioInput.rain_change_pct>0?"+":""}{scenarioInput.rain_change_pct}%</b><input type="range" min="-50" max="200" value={scenarioInput.rain_change_pct} onChange={e=>setScenarioInput({...scenarioInput,rain_change_pct:+e.target.value})}/></label><label>하수관 수위 <b>{scenarioInput.sewer_change_pct>0?"+":""}{scenarioInput.sewer_change_pct}%</b><input type="range" min="-50" max="100" value={scenarioInput.sewer_change_pct} onChange={e=>setScenarioInput({...scenarioInput,sewer_change_pct:+e.target.value})}/></label><label>하천 수위 <b>{scenarioInput.river_change_pct>0?"+":""}{scenarioInput.river_change_pct}%</b><input type="range" min="-50" max="100" value={scenarioInput.river_change_pct} onChange={e=>setScenarioInput({...scenarioInput,river_change_pct:+e.target.value})}/></label><button className="scenario-run" onClick={runScenario} disabled={scenarioBusy}>{scenarioBusy?"서울 LH 단지 시나리오 분석 중…":"시나리오 실행"}</button><button className="scenario-reset" onClick={()=>{setScenario(null);setScenarioInput({scenario_name:"",rain_change_pct:0,sewer_change_pct:0,river_change_pct:0})}}>초기화</button></div>{scenarioError&&<div className="error-box">{scenarioError}</div>}<p>※ 시나리오 모드는 사용자가 입력한 조건에 따른 재난 Stress Test입니다. 실제 기상예보 또는 미래 재난 발생확률을 의미하지 않습니다.</p></section>}
    {mode === "scenario" && scenario ? <div className="kpi-grid scenario-kpis"><ScenarioKpi label="분석 대상 LH 단지" before={scenario.base_summary.total} after={scenario.scenario_summary.total}/><ScenarioKpi label="취약 단지" before={scenario.base_summary.vulnerable} after={scenario.scenario_summary.vulnerable}/><ScenarioKpi label="주의 단지" before={scenario.base_summary.caution} after={scenario.scenario_summary.caution}/><ScenarioKpi label="평균 Re:Safe Score" before={scenario.base_summary.average_resilience_score} after={scenario.scenario_summary.average_resilience_score}/></div> : <div className="kpi-grid"><Kpi icon={<Building2/>} label="전체 LH 단지" value={rows.length} color="#2575eb" active={activeKpi==="all"} onClick={()=>setActiveKpi(activeKpi==="all"?null:"all")}/><Kpi icon={<ShieldCheck/>} label="분석 가능 단지" value={eligible} color="#22a06b" active={activeKpi==="eligible"} onClick={()=>setActiveKpi(activeKpi==="eligible"?null:"eligible")}/><Kpi icon={<TriangleAlert/>} label="회복력 취약" value={vulnerable} color="#e5484d" active={activeKpi==="vulnerable"} onClick={()=>setActiveKpi(activeKpi==="vulnerable"?null:"vulnerable")}/><Kpi icon={<Bell/>} label="데이터 보강 필요" value={insufficient} color="#7c4dff" active={activeKpi==="insufficient"} onClick={()=>setActiveKpi(activeKpi==="insufficient"?null:"insufficient")}/></div>}
    {selectedKpi && <KpiDetail title={selectedKpi.title} description={selectedKpi.description} rows={selectedKpi.rows} onClose={()=>setActiveKpi(null)} onSelect={onSelect}/>}
    <div className="dashboard-grid"><section className="panel map-panel"><div className="panel-head"><h2>LH 단지 위험 현황 지도</h2><span>{mode==="scenario"&&scenario?"SCENARIO · 사용자 입력값":"실데이터 기준"}</span></div><NaverMap rows={displayRows} onSelect={onSelect}/></section><section className="panel"><div className="panel-head"><h2>{mode==="scenario"&&scenario?"시나리오 영향 TOP 5":"현재 점검 우선 단지"}</h2><span>{mode==="scenario"&&scenario?impactRows.length:highRisk.length}개</span></div><div className="risk-list">{mode==="scenario"&&scenario?impactRows.map((s:any)=>{const x=rows.find(r=>r.complex_id===s.complex_id);return <button key={s.complex_id} onClick={()=>x&&onSelect(x)}><i style={{background:riskColor(s.scenario_resilience_score)}}/><div><b>{s.complex_name}</b><span>{fmt(s.base_resilience_score)} → {fmt(s.scenario_resilience_score)}</span></div><strong>{s.resilience_delta?.toFixed(1)}</strong><ChevronRight/></button>}):highRisk.slice(0,6).map(x=><button key={x.complex_id} onClick={()=>onSelect(x)}><i style={{background:riskColor(x.resilience_score)}}/><div><b>{x.complex_name}</b><span>{x.address}</span></div><strong>{fmt(x.resilience_score)}</strong><ChevronRight/></button>)}</div></section></div>
    <div className="lower-grid"><Distribution rows={rows}/><section className="panel"><div className="panel-head"><h2>최근 취약 단지</h2></div><CompactTable rows={highRisk.slice(0,7)} onSelect={onSelect}/></section></div>
  </Page>;
}

function Kpi({ icon, label, value, color, active=false, onClick }: { icon: React.ReactNode; label: string; value: number; color: string; active?: boolean; onClick?: ()=>void }) { const content=<><span style={{color, background:`${color}18`}}>{icon}</span><div><small>{label}</small><strong>{value.toLocaleString()}<em>개</em></strong><p>{onClick?"클릭하여 상세 보기":"검증 완료 운영 DB 기준"}</p></div>{onClick&&<ChevronRight className="kpi-arrow"/>}</>; return onClick?<button type="button" className={`kpi kpi-button ${active?"active":""}`} onClick={onClick} aria-expanded={active}>{content}</button>:<div className="kpi">{content}</div>; }
function ScenarioKpi({label,before,after}:{label:string;before:number|null;after:number|null}) { const delta=before!=null&&after!=null?after-before:null; return <div className="kpi scenario-kpi"><div><small>{label}</small><strong>{before==null?"–":before.toFixed(1)} <em>→</em> {after==null?"–":after.toFixed(1)}</strong><p>{delta==null?"데이터 부족":`${delta>0?"▲ ":delta<0?"▼ ":""}${delta>0?"+":""}${delta.toFixed(1)}`}</p></div></div>; }

function KpiDetail({title,description,rows,onClose,onSelect}:{title:string;description:string;rows:Complex[];onClose:()=>void;onSelect:(x:Complex)=>void}) { const scored=rows.filter(x=>x.resilience_score!=null); const confident=rows.filter(x=>x.data_confidence!=null); const avg=(items:Complex[],field:"resilience_score"|"data_confidence")=>items.length?items.reduce((sum,x)=>sum+Number(x[field]||0),0)/items.length:null; const districts=Object.entries(rows.reduce<Record<string,number>>((acc,x)=>{const key=x.district||"미확인";acc[key]=(acc[key]||0)+1;return acc;},{})).sort((a,b)=>b[1]-a[1]).slice(0,5); return <section className="panel kpi-detail" aria-live="polite"><div className="detail-head"><div><span className="eyebrow">KPI 상세</span><h2>{title}</h2><p>{description}</p></div><button className="icon-button" onClick={onClose} aria-label="상세 닫기"><XCircle/></button></div><div className="kpi-detail-summary"><div><small>해당 단지</small><b>{rows.length.toLocaleString()}개</b></div><div><small>평균 회복력</small><b>{avg(scored,"resilience_score")?.toFixed(1)??"미산정"}</b></div><div><small>평균 데이터 신뢰도</small><b>{avg(confident,"data_confidence")?.toFixed(1)??"미산정"}</b></div><div><small>주요 지역</small><b>{districts[0]?.[0]||"미확인"}</b></div></div>{districts.length>0&&<div className="district-chips">{districts.map(([name,count])=><span key={name}>{name} <b>{count}</b></span>)}</div>}<div className="kpi-detail-table"><CompactTable rows={rows.slice(0,100)} onSelect={onSelect}/></div>{rows.length>100&&<p className="table-note">상위 100개 단지만 표시합니다. 검색창으로 원하는 단지를 좁힐 수 있습니다.</p>}</section>; }
function Distribution({ rows }: { rows: Complex[] }) {
  const groups = [{n:"취약",c:"#e53935",f:(x:Complex)=>x.resilience_score!=null&&x.resilience_score<=39},{n:"주의",c:"#fb8c00",f:(x:Complex)=>x.resilience_score!=null&&x.resilience_score>39&&x.resilience_score<=59},{n:"보통",c:"#f6c945",f:(x:Complex)=>x.resilience_score!=null&&x.resilience_score>59&&x.resilience_score<=74},{n:"양호",c:"#35b987",f:(x:Complex)=>x.resilience_score!=null&&x.resilience_score>74},{n:"미분석",c:"#91a3bc",f:(x:Complex)=>x.resilience_score==null}].map(g=>({...g,v:rows.filter(g.f).length}));
  let cursor=0; const stops=groups.map(g=>{const start=cursor;cursor+=rows.length?g.v/rows.length*360:0;return `${g.c} ${start}deg ${cursor}deg`;}).join(",");
  return <section className="panel"><div className="panel-head"><h2>회복력 분포</h2></div><div className="donut-area"><div className="donut" style={{background:`conic-gradient(${stops})`}}><div><b>{rows.length}</b><span>전체 단지</span></div></div><div className="legend">{groups.map(g=><div key={g.n}><i style={{background:g.c}}/><span>{g.n}</span><b>{g.v}개</b></div>)}</div></div></section>;
}
function CompactTable({ rows, onSelect }: { rows: Complex[]; onSelect: (x: Complex)=>void }) { return <div className="table"><div className="tr th"><span>단지명</span><span>지역</span><span>등급</span><span>회복력</span></div>{rows.map(x=><button className="tr" key={x.complex_id} onClick={()=>onSelect(x)}><b>{x.complex_name}</b><span>{x.district||"미확인"}</span><span className="badge" style={{color:riskColor(x.resilience_score)}}>{x.resilience_grade||"미분석"}</span><strong>{fmt(x.resilience_score)}</strong></button>)}</div>; }

function ComplexList({rows,onSelect}:{rows:Complex[];onSelect:(x:Complex)=>void}) { return <Page title="단지 회복력 분석" subtitle="운영 DB에 적재된 서울 LH 단지와 상세 검증 근거입니다."><section className="panel"><CompactTable rows={rows} onSelect={onSelect}/></section></Page>; }
function ComplexAnalysis({rows,title,onSelect}:{rows:Complex[];title:string;onSelect:(x:Complex)=>void}) { return <Page title={title} subtitle="단지를 선택하면 수치와 원본 근거를 즉시 조회합니다."><div className="card-grid">{rows.slice(0,24).map(x=><button className="complex-card" key={x.complex_id} onClick={()=>onSelect(x)}><i style={{background:riskColor(x.resilience_score)}}/><div><b>{x.complex_name}</b><span>{x.address}</span></div><strong>{fmt(x.resilience_score)}</strong></button>)}</div></Page>; }

function RiskFeed({predictions,complexes,onSelect}:{predictions:Prediction[];complexes:Complex[];onSelect:(x:Complex)=>void}) {
  const [grade,setGrade]=useState("전체");
  const [type,setType]=useState("전체");
  const [district,setDistrict]=useState("전체");
  const [sort,setSort]=useState("위험도순");
  const predictionByComplex=useMemo(()=>new globalThis.Map<string,Prediction>(predictions.map(x=>[x.complex_id,x])),[predictions]);
  const level=(x:Complex)=>x.resilience_score==null?"데이터 이상":x.resilience_score<=39?"심각":x.resilience_score<=59?"높음":x.resilience_score<=74?"주의":"정보";
  const danger=(x:Complex)=>x.resilience_score==null?null:Math.max(0,Math.min(100,100-x.resilience_score));
  const districts=useMemo(()=>Array.from(new Set(complexes.map(x=>x.district).filter(Boolean) as string[])).sort(),[complexes]);
  const rows=useMemo(()=>complexes.map(complex=>({complex,prediction:predictionByComplex.get(complex.complex_id)})).filter(({complex,prediction})=>{
    const riskType=prediction?.risk_type||"기준선";
    return (grade==="전체"||level(complex)===grade)&&(type==="전체"||riskType===type)&&(district==="전체"||complex.district===district);
  }).sort((a,b)=>sort==="최신순"?String(b.prediction?.prediction_time||b.complex.assessed_at||"").localeCompare(String(a.prediction?.prediction_time||a.complex.assessed_at||"")):(danger(b.complex)??-1)-(danger(a.complex)??-1)),[complexes,predictionByComplex,grade,type,district,sort]);
  const severe=complexes.filter(x=>level(x)==="심각").length;
  const high=complexes.filter(x=>level(x)==="높음").length;
  const caution=complexes.filter(x=>level(x)==="주의").length;
  const dataIssue=complexes.filter(x=>level(x)==="데이터 이상").length;
  const groups=[{name:"심각",value:severe,color:"#ef4444"},{name:"높음",value:high,color:"#f97316"},{name:"주의",value:caution,color:"#fbbf24"},{name:"정보",value:complexes.length-severe-high-caution-dataIssue,color:"#3b82f6"},{name:"데이터 이상",value:dataIssue,color:"#8b5cf6"}];
  let cursor=0; const stops=groups.map(g=>{const start=cursor;cursor+=complexes.length?g.value/complexes.length*360:0;return `${g.color} ${start}deg ${cursor}deg`;}).join(",");
  const types=Array.from(new Set(predictions.map(x=>x.risk_type).filter(Boolean)));
  const kpis=[
    {label:"운영 경보",value:predictions.length,icon:<Siren/>,color:"#ef4444"},
    {label:"고위험 단지",value:severe+high,icon:<ShieldCheck/>,color:"#f97316"},
    {label:"주의 단지",value:caution,icon:<Droplets/>,color:"#fbbf24"},
    {label:"시설 점검 필요",value:complexes.filter(x=>x.resilience_score!=null&&x.resilience_score<=59).length,icon:<Wrench/>,color:"#3b82f6"},
    {label:"데이터 이상",value:dataIssue,icon:<Database/>,color:"#8b5cf6"}
  ];
  return <Page title="AI 재난 위험 피드" subtitle="실데이터 기반 경보를 제공합니다. Baseline(기준선) 결과와 검증된 ML 결과를 구분해 표시합니다.">
    <div className="feed-kpis">{kpis.map(k=><div className="feed-kpi" key={k.label}><span style={{background:`${k.color}18`,color:k.color}}>{k.icon}</span><div><small>{k.label}</small><strong>{k.value.toLocaleString()}<em>건</em></strong><p>현재 적재 데이터 기준</p></div></div>)}</div>
    <div className="feed-toolbar"><label>위험등급<select value={grade} onChange={e=>setGrade(e.target.value)}><option>전체</option>{groups.map(g=><option key={g.name}>{g.name}</option>)}</select></label><label>데이터 유형<select value={type} onChange={e=>setType(e.target.value)}><option>전체</option><option>기준선</option>{types.map(x=><option key={x}>{x}</option>)}</select></label><label>자치구<select value={district} onChange={e=>setDistrict(e.target.value)}><option>전체</option>{districts.map(x=><option key={x}>{x}</option>)}</select></label><label>정렬 기준<select value={sort} onChange={e=>setSort(e.target.value)}><option>위험도순</option><option>최신순</option></select></label></div>
    <div className="feed-layout"><section className="feed-list">{rows.length?rows.slice(0,50).map(({complex,prediction})=>{const score=danger(complex);const riskLevel=level(complex);const color=groups.find(g=>g.name===riskLevel)?.color||"#64748b";return <button className="feed-alert" key={complex.complex_id} onClick={()=>onSelect(complex)}><span className="feed-level" style={{background:`${color}18`,color}}><TriangleAlert/>{riskLevel}</span><div className="feed-main"><div><b>{complex.complex_name}</b><small>{complex.district||"자치구 미확인"}</small><time>{prediction?.prediction_time?new Date(prediction.prediction_time).toLocaleString("ko-KR"):complex.assessed_at?new Date(complex.assessed_at).toLocaleString("ko-KR"):"평가시각 미확인"}</time></div><p>{prediction?`${prediction.risk_type} 모델이 위험 신호를 탐지했습니다.`:"회복력 지수와 데이터 품질을 기준으로 우선 확인이 필요한 단지입니다."}</p><footer><span><Activity/>위험도 <b>{score==null?"미분석":`${score.toFixed(0)}%`}</b></span><span><Database/>신뢰도 <b>{complex.data_confidence==null?"미확인":`${complex.data_confidence.toFixed(0)}%`}</b></span><span className={prediction?"model ml":"model"}>{prediction?"ML 예측":"Baseline"}</span></footer></div><ChevronRight/></button>}):<Empty text="선택한 조건에 해당하는 경보가 없습니다."/>}</section>
      <aside className="feed-side"><section className="feed-side-card"><div className="feed-side-head"><h2>실시간 상황 요약</h2><span>{new Date().toLocaleString("ko-KR")}</span></div><dl><div><dt>모니터링 단지</dt><dd>{complexes.length}개</dd></div><div><dt>점검 필요 단지</dt><dd className="danger">{severe+high}개</dd></div><div><dt>검증된 ML 경보</dt><dd>{predictions.length}건</dd></div><div><dt>좌표 확인 완료</dt><dd>{complexes.filter(x=>x.latitude!=null&&x.longitude!=null).length}개</dd></div></dl></section>
      <section className="feed-side-card"><div className="feed-side-head"><h2>위험도 분포</h2><span>전체 단지 기준</span></div><div className="feed-donut-row"><div className="feed-donut" style={{background:`conic-gradient(${stops})`}}><div><b>{complexes.length}</b><small>전체</small></div></div><div className="feed-legend">{groups.map(g=><div key={g.name}><i style={{background:g.color}}/><span>{g.name}</span><b>{g.value}개</b></div>)}</div></div></section>
      <section className="feed-side-card"><div className="feed-side-head"><h2>점검 우선순위 TOP 5</h2><span>위험도 기준</span></div><ol className="feed-ranking">{[...complexes].sort((a,b)=>(danger(b)??-1)-(danger(a)??-1)).slice(0,5).map((x,i)=><li key={x.complex_id}><i>{i+1}</i><button onClick={()=>onSelect(x)}><b>{x.complex_name}</b><span>{x.district||"미확인"}</span><strong style={{color:riskColor(x.resilience_score)}}>{level(x)}</strong><em>{danger(x)?.toFixed(0)??"-"}%</em></button></li>)}</ol></section></aside>
    </div>
  </Page>;
}

function AiChat({complexes}:{complexes:Complex[]}) { const [target,setTarget]=useState(""); const [input,setInput]=useState(""); const [messages,setMessages]=useState<{role:string;text:string}[]>([]); const [busy,setBusy]=useState(false); const submit=async()=>{if(!input.trim())return;const q=input;setInput("");setMessages(m=>[...m,{role:"user",text:q}]);setBusy(true);try{const r=await api<any>("/api/v1/ai/chat",{method:"POST",body:JSON.stringify({question:q,complex_id:target||null,scenario_id:sessionStorage.getItem("active_scenario_id")})});setMessages(m=>[...m,{role:"ai",text:r.answer}]);}catch(e:any){setMessages(m=>[...m,{role:"ai",text:`오류: ${e.message}`}]);}finally{setBusy(false)}};return <Page title="AI Chat" subtitle="Claude가 운영 DB의 검증 근거를 바탕으로 답변합니다."><section className="panel chat"><select value={target} onChange={e=>setTarget(e.target.value)}><option value="">전체 단지</option>{complexes.map(x=><option value={x.complex_id} key={x.complex_id}>{x.complex_name}</option>)}</select><div className="messages">{messages.length?messages.map((m,i)=><div className={m.role} key={i}>{m.text}</div>):<Empty text="질문을 입력하면 근거 기반 답변이 표시됩니다."/>}</div><div className="chat-input"><input value={input} onChange={e=>setInput(e.target.value)} onKeyDown={e=>e.key==="Enter"&&submit()} placeholder="안전·침수·시설 관련 질문"/><button onClick={submit} disabled={busy}><Send/></button></div></section></Page>; }

function Reports({complexes}:{complexes:Complex[]}) {
  const [reportType,setReportType]=useState("resilience");
  const [scopeType,setScopeType]=useState("seoul");
  const [district,setDistrict]=useState("");
  const [target,setTarget]=useState("");
  const [referenceDate,setReferenceDate]=useState("");
  const [created,setCreated]=useState<any>(null);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const districts=useMemo(()=>Array.from(new Set(complexes.map(x=>x.district).filter(Boolean) as string[])).sort(),[complexes]);
  const candidates=useMemo(()=>district?complexes.filter(x=>x.district===district):complexes,[complexes,district]);
  const create=async()=>{
    const scopeValue=scopeType==="district"?district:scopeType==="complex"?target:null;
    if(scopeType!=="seoul"&&!scopeValue){setError(scopeType==="district"?"자치구를 선택하세요.":"단지를 선택하세요.");return;}
    setBusy(true);setError("");
    try{setCreated(await api<any>("/api/v1/seoul/reports/generate",{method:"POST",body:JSON.stringify({report_type:reportType,scope_type:scopeType,scope_value:scopeValue,reference_date:referenceDate||null})}));}
    catch(e:any){setError(e.message||String(e));}
    finally{setBusy(false);}
  };
  const summary=created?.summary;
  return <Page title="AI 보고서" subtitle="서울·자치구·단지 단위의 운영 DB 근거를 스냅샷으로 저장하고 HTML/PDF 보고서를 생성합니다.">
    <section className="panel report-builder">
      <div className="report-controls">
        <label>보고서 유형<select value={reportType} onChange={e=>setReportType(e.target.value)}><option value="resilience">종합 회복력</option><option value="climate">기후재난</option><option value="facility">시설 취약성</option><option value="cascade">복합재난 연쇄영향</option></select></label>
        <label>분석 범위<select value={scopeType} onChange={e=>{setScopeType(e.target.value);setCreated(null)}}><option value="seoul">서울 전체</option><option value="district">자치구</option><option value="complex">개별 단지</option></select></label>
        {scopeType!=="seoul"&&<label>자치구<select value={district} onChange={e=>{setDistrict(e.target.value);setTarget("")}}><option value="">선택</option>{districts.map(x=><option key={x}>{x}</option>)}</select></label>}
        {scopeType==="complex"&&<label>단지<select value={target} onChange={e=>setTarget(e.target.value)}><option value="">선택</option>{candidates.map(x=><option value={x.complex_id} key={x.complex_id}>{x.complex_name}</option>)}</select></label>}
        <label>기준일<input type="date" value={referenceDate} onChange={e=>setReferenceDate(e.target.value)}/></label>
        <button className="primary" onClick={create} disabled={busy}>{busy?"검증·생성 중…":"보고서 생성"}</button>
      </div>
      {error&&<div className="error-box">{error}</div>}
    </section>
    {!created?<section className="panel report-empty"><FileText/><b>생성된 보고서가 없습니다.</b><span>범위를 선택하면 실제 DB에서 집계하고 결과 스냅샷을 저장합니다.</span></section>:
    <div className="report-result">
      <section className="panel report-title"><div><span className="eyebrow">{created.report_type_label}</span><h2>{created.scope.label}</h2><p>기준 시각 {created.reference_time?new Date(created.reference_time).toLocaleString("ko-KR"):"데이터 부족"} · {created.freshness}</p></div><div className="report-downloads"><a href={created.html_download_url}>HTML 다운로드</a><a className="primary" href={created.pdf_download_url}>PDF 다운로드</a></div></section>
      <div className="report-kpis"><Kpi icon={<Building2/>} label="대상 단지" value={summary.total_complexes} color="#2575eb"/><Kpi icon={<ShieldCheck/>} label="분석 가능" value={summary.analysis_available} color="#22a06b"/><Kpi icon={<TriangleAlert/>} label="취약·주의" value={summary.vulnerable+summary.caution} color="#e5484d"/><Kpi icon={<Database/>} label="데이터 부족" value={summary.insufficient} color="#7c4dff"/></div>
      <div className="report-grid">
        <section className="panel"><div className="panel-head"><h2>AI 근거 해설</h2><span>Claude 실패 시 규칙 기반 해설</span></div><p className="report-explanation">{created.ai_explanation}</p></section>
        <section className="panel"><div className="panel-head"><h2>핵심 지표</h2></div><dl className="report-metrics"><div><dt>평균 Re:Safe</dt><dd>{summary.average_resilience??"데이터 부족"}</dd></div><div><dt>취약</dt><dd>{summary.vulnerable}개</dd></div><div><dt>주의</dt><dd>{summary.caution}개</dd></div><div><dt>양호</dt><dd>{summary.good}개</dd></div></dl></section>
      </div>
      {scopeType==="complex"&&created.detail?.profile?.latitude!=null&&<section className="panel report-map"><div className="panel-head"><h2>선택 단지 위치</h2></div><NaverMap rows={complexes.filter(x=>x.complex_id===target)} onSelect={()=>{}}/></section>}
      <div className="report-grid">
        <section className="panel"><div className="panel-head"><h2>주요 발견사항</h2></div><ol className="report-list">{created.findings.length?created.findings.map((x:any,i:number)=><li key={i}>{x.text}</li>):<li>확정 가능한 추가 발견사항 없음</li>}</ol></section>
        <section className="panel"><div className="panel-head"><h2>우선 권고사항</h2></div><ol className="report-list">{created.recommendations.length?created.recommendations.map((x:any)=><li key={x.priority}><b>{x.priority}순위</b> {x.text}<small>{x.reason}</small></li>):<li>현재 근거에서 추가 권고사항 없음</li>}</ol></section>
      </div>
      <section className="panel"><div className="panel-head"><h2>취약 단지 순위</h2><span>낮은 회복력 점수 순</span></div><div className="table"><div className="tr th"><span>단지명</span><span>자치구</span><span>등급</span><span>점수</span></div>{created.ranking.map((x:any)=><div className="tr" key={x.complex_id}><b>{x.complex_name}</b><span>{x.district||"미확인"}</span><span>{x.grade}</span><strong>{x.score}</strong></div>)}</div></section>
      <section className="panel report-foot"><div><h2>데이터 출처</h2>{created.data_sources.map((x:any)=><span key={x.name}>{x.name} · {x.status}</span>)}</div><div><h2>분석 한계</h2>{created.limitations.map((x:string,i:number)=><p key={i}>· {x}</p>)}</div></section>
    </div>}
  </Page>;
}
function DataManagement({quality,hydrology}:{quality:any;hydrology:any}) {
  const runs:any[]=quality?.collection_runs||[];
  const latestRuns=Array.from(runs.reduce((latest:Map<string,any>,run:any)=>{
    if(!latest.has(run.dataset_id)) latest.set(run.dataset_id,{...run,previousFailures:0});
    else if(run.status==="failed") latest.get(run.dataset_id).previousFailures+=1;
    return latest;
  },new globalThis.Map<string,any>()).values());
  const configured=Object.entries(hydrology?.configuration||{});
  const available=Object.entries(hydrology?.availability||{});
  return <Page title="데이터 관리" subtitle="API 설정과 실제 적재 데이터 상태를 구분해 확인합니다.">
    <div className="kpi-grid"><Kpi icon={<Database/>} label="전체 단지" value={quality?.complex_count||0} color="#2575eb"/><Kpi icon={<CheckCircle2/>} label="API 수집 준비" value={configured.filter(([,v]:any)=>v.collection_ready).length} color="#22a06b"/><Kpi icon={<Database/>} label="적재 데이터" value={available.filter(([,v]:any)=>v.status==="AVAILABLE").length} color="#2575eb"/><Kpi icon={<XCircle/>} label="확인 필요" value={available.filter(([,v]:any)=>v.status!=="AVAILABLE").length} color="#e5484d"/></div>
    <section className="panel"><div className="panel-head"><h2>API 연결 설정</h2><span>키 값은 브라우저에 노출하지 않습니다</span></div><div className="source-grid">{configured.map(([name,value]:any)=><div className="source-card" key={name}><span className={`source-dot ${value.collection_ready?"ready":"blocked"}`}/><div><b>{name}</b><small>{value.collection_ready?"키·URL 설정 완료":"키 또는 URL 확인 필요"}</small></div></div>)}</div></section>
    <section className="panel"><div className="panel-head"><h2>파일/API 적재 상태</h2></div><div className="source-grid">{available.map(([name,value]:any)=><div className="source-card" key={name}><span className={`source-dot ${value.status==="AVAILABLE"?"ready":"blocked"}`}/><div><b>{name}</b><small>{value.status} · {value.file_count||0}개 파일</small></div></div>)}</div></section>
    <section className="panel"><div className="panel-head"><h2>데이터셋별 최신 수집 상태</h2><span>과거 실패는 감사 이력으로 보존됩니다</span></div><div className="data-runs">{latestRuns.slice(0,30).map((x:any)=><div key={x.collection_run_id}><span className={`status ${x.status}`}>{x.status}</span><b>{x.dataset_id}</b><span>{x.record_count||0}건</span><small>{x.failure_reason||"검증 완료"}{x.previousFailures>0?` · 과거 실패 ${x.previousFailures}회`:""}</small></div>)}</div></section>
  </Page>;
}
function SystemSettings({models}:{models:any}) { return <Page title="시스템 설정" subtitle="외부 서비스와 모델 운영 상태입니다."><section className="panel"><h2>모델 상태</h2><div className="data-runs">{(models?.items||[]).map((x:any)=><div key={x.model_id}><span className={`status ${x.status}`}>{x.status}</span><b>{x.model_name}</b><small>{x.status_reason}</small></div>)}</div></section><section className="panel help"><h2>지도 설정</h2><p>NAVER 지도 Client ID와 인증 방식은 프로젝트 <code>.env</code>에서 관리합니다. 비밀키는 브라우저로 전달하지 않습니다.</p></section></Page>; }
function Empty({text}:{text:string}) { return <div className="empty"><ShieldCheck/><b>{text}</b><span>데이터 상태를 확인하거나 새로고침하십시오.</span></div>; }
