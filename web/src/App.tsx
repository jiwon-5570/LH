import { useCallback, useEffect, useMemo, useState } from "react";
import {
  LayoutDashboard, Map, TriangleAlert, Building2, CloudRain, Wrench, BrainCircuit,
  FileText, Database, Settings, Search, Bell, RefreshCw, CheckCircle2, XCircle,
  ShieldCheck, ChevronRight, Send
} from "lucide-react";
import { api, fmt, riskColor, type Complex, type Prediction } from "./api";
import { NaverMap } from "./NaverMap";
import { DetailPanel } from "./DetailPanel";

const menus = [
  ["대시보드", LayoutDashboard], ["지도 보기", Map], ["AI 재난 위험 피드", TriangleAlert],
  ["단지 회복력 분석", Building2], ["기후재난 분석", CloudRain], ["시설 취약도", Wrench],
  ["AI 안전 관제", BrainCircuit], ["AI 회복력 보고서", FileText], ["데이터 관리", Database], ["시스템 설정", Settings]
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
        {page === "AI 재난 위험 피드" && <RiskFeed predictions={predictions} complexes={complexes}/>}
        {page === "단지 회복력 분석" && <ComplexList rows={filtered} onSelect={setSelected}/>}
        {page === "기후재난 분석" && <ComplexAnalysis rows={filtered} title="기후재난 분석" onSelect={setSelected}/>}
        {page === "시설 취약도" && <ComplexAnalysis rows={filtered} title="시설 취약도" onSelect={setSelected}/>}
        {page === "AI 안전 관제" && <AiChat complexes={complexes}/>}
        {page === "AI 회복력 보고서" && <Reports complexes={complexes}/>}
        {page === "데이터 관리" && <DataManagement quality={quality} hydrology={hydrology}/>}
        {page === "시스템 설정" && <SystemSettings models={models}/>}
        {selected && <DetailPanel complex={selected} onClose={() => setSelected(null)}/>}
      </div>
    </main>
  </div>;
}

function Page({ title, subtitle, children }: { title: string; subtitle: string; children: React.ReactNode }) { return <><div className="page-title"><div><h1>{title}</h1><p>{subtitle}</p></div></div>{children}</>; }

function Dashboard({ rows, highRisk, onSelect }: { rows: Complex[]; highRisk: Complex[]; onSelect: (x: Complex) => void }) {
  type KpiKey = "all" | "eligible" | "vulnerable" | "insufficient";
  const [activeKpi, setActiveKpi] = useState<KpiKey | null>(null);
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
  return <Page title="통합 안전 관리 대시보드" subtitle="서울 LH 단지의 재난·설비 위험과 데이터 품질을 한눈에 확인합니다.">
    <div className="kpi-grid"><Kpi icon={<Building2/>} label="전체 LH 단지" value={rows.length} color="#2575eb" active={activeKpi==="all"} onClick={()=>setActiveKpi(activeKpi==="all"?null:"all")}/><Kpi icon={<ShieldCheck/>} label="분석 가능 단지" value={eligible} color="#22a06b" active={activeKpi==="eligible"} onClick={()=>setActiveKpi(activeKpi==="eligible"?null:"eligible")}/><Kpi icon={<TriangleAlert/>} label="회복력 취약" value={vulnerable} color="#e5484d" active={activeKpi==="vulnerable"} onClick={()=>setActiveKpi(activeKpi==="vulnerable"?null:"vulnerable")}/><Kpi icon={<Bell/>} label="데이터 보강 필요" value={insufficient} color="#7c4dff" active={activeKpi==="insufficient"} onClick={()=>setActiveKpi(activeKpi==="insufficient"?null:"insufficient")}/></div>
    {selectedKpi && <KpiDetail title={selectedKpi.title} description={selectedKpi.description} rows={selectedKpi.rows} onClose={()=>setActiveKpi(null)} onSelect={onSelect}/>}
    <div className="dashboard-grid"><section className="panel map-panel"><div className="panel-head"><h2>LH 단지 위험 현황 지도</h2><span>실데이터 기준</span></div><NaverMap rows={rows} onSelect={onSelect}/></section><section className="panel"><div className="panel-head"><h2>점검 우선 단지</h2><span>{highRisk.length}개</span></div><div className="risk-list">{highRisk.slice(0, 6).map(x => <button key={x.complex_id} onClick={() => onSelect(x)}><i style={{background:riskColor(x.resilience_score)}}/><div><b>{x.complex_name}</b><span>{x.address}</span></div><strong>{fmt(x.resilience_score)}</strong><ChevronRight/></button>)}</div></section></div>
    <div className="lower-grid"><Distribution rows={rows}/><section className="panel"><div className="panel-head"><h2>최근 취약 단지</h2></div><CompactTable rows={highRisk.slice(0,7)} onSelect={onSelect}/></section></div>
  </Page>;
}

function Kpi({ icon, label, value, color, active=false, onClick }: { icon: React.ReactNode; label: string; value: number; color: string; active?: boolean; onClick?: ()=>void }) { const content=<><span style={{color, background:`${color}18`}}>{icon}</span><div><small>{label}</small><strong>{value.toLocaleString()}<em>개</em></strong><p>{onClick?"클릭하여 상세 보기":"검증 완료 운영 DB 기준"}</p></div>{onClick&&<ChevronRight className="kpi-arrow"/>}</>; return onClick?<button type="button" className={`kpi kpi-button ${active?"active":""}`} onClick={onClick} aria-expanded={active}>{content}</button>:<div className="kpi">{content}</div>; }

function KpiDetail({title,description,rows,onClose,onSelect}:{title:string;description:string;rows:Complex[];onClose:()=>void;onSelect:(x:Complex)=>void}) { const scored=rows.filter(x=>x.resilience_score!=null); const confident=rows.filter(x=>x.data_confidence!=null); const avg=(items:Complex[],field:"resilience_score"|"data_confidence")=>items.length?items.reduce((sum,x)=>sum+Number(x[field]||0),0)/items.length:null; const districts=Object.entries(rows.reduce<Record<string,number>>((acc,x)=>{const key=x.district||"미확인";acc[key]=(acc[key]||0)+1;return acc;},{})).sort((a,b)=>b[1]-a[1]).slice(0,5); return <section className="panel kpi-detail" aria-live="polite"><div className="detail-head"><div><span className="eyebrow">KPI 상세</span><h2>{title}</h2><p>{description}</p></div><button className="icon-button" onClick={onClose} aria-label="상세 닫기"><XCircle/></button></div><div className="kpi-detail-summary"><div><small>해당 단지</small><b>{rows.length.toLocaleString()}개</b></div><div><small>평균 회복력</small><b>{avg(scored,"resilience_score")?.toFixed(1)??"미산정"}</b></div><div><small>평균 데이터 신뢰도</small><b>{avg(confident,"data_confidence")?.toFixed(1)??"미산정"}</b></div><div><small>주요 지역</small><b>{districts[0]?.[0]||"미확인"}</b></div></div>{districts.length>0&&<div className="district-chips">{districts.map(([name,count])=><span key={name}>{name} <b>{count}</b></span>)}</div>}<div className="kpi-detail-table"><CompactTable rows={rows.slice(0,100)} onSelect={onSelect}/></div>{rows.length>100&&<p className="table-note">상위 100개 단지만 표시합니다. 검색창으로 원하는 단지를 좁힐 수 있습니다.</p>}</section>; }
function Distribution({ rows }: { rows: Complex[] }) {
  const groups = [{n:"취약",c:"#e53935",f:(x:Complex)=>x.resilience_score!=null&&x.resilience_score<=39},{n:"주의",c:"#fb8c00",f:(x:Complex)=>x.resilience_score!=null&&x.resilience_score>39&&x.resilience_score<=59},{n:"보통",c:"#f6c945",f:(x:Complex)=>x.resilience_score!=null&&x.resilience_score>59&&x.resilience_score<=74},{n:"양호",c:"#35b987",f:(x:Complex)=>x.resilience_score!=null&&x.resilience_score>74},{n:"미분석",c:"#91a3bc",f:(x:Complex)=>x.resilience_score==null}].map(g=>({...g,v:rows.filter(g.f).length}));
  let cursor=0; const stops=groups.map(g=>{const start=cursor;cursor+=rows.length?g.v/rows.length*360:0;return `${g.c} ${start}deg ${cursor}deg`;}).join(",");
  return <section className="panel"><div className="panel-head"><h2>회복력 분포</h2></div><div className="donut-area"><div className="donut" style={{background:`conic-gradient(${stops})`}}><div><b>{rows.length}</b><span>전체 단지</span></div></div><div className="legend">{groups.map(g=><div key={g.n}><i style={{background:g.c}}/><span>{g.n}</span><b>{g.v}개</b></div>)}</div></div></section>;
}
function CompactTable({ rows, onSelect }: { rows: Complex[]; onSelect: (x: Complex)=>void }) { return <div className="table"><div className="tr th"><span>단지명</span><span>지역</span><span>등급</span><span>회복력</span></div>{rows.map(x=><button className="tr" key={x.complex_id} onClick={()=>onSelect(x)}><b>{x.complex_name}</b><span>{x.district||"미확인"}</span><span className="badge" style={{color:riskColor(x.resilience_score)}}>{x.resilience_grade||"미분석"}</span><strong>{fmt(x.resilience_score)}</strong></button>)}</div>; }

function ComplexList({rows,onSelect}:{rows:Complex[];onSelect:(x:Complex)=>void}) { return <Page title="단지 회복력 분석" subtitle="운영 DB에 적재된 서울 LH 단지와 상세 검증 근거입니다."><section className="panel"><CompactTable rows={rows} onSelect={onSelect}/></section></Page>; }
function ComplexAnalysis({rows,title,onSelect}:{rows:Complex[];title:string;onSelect:(x:Complex)=>void}) { return <Page title={title} subtitle="단지를 선택하면 수치와 원본 근거를 즉시 조회합니다."><div className="card-grid">{rows.slice(0,24).map(x=><button className="complex-card" key={x.complex_id} onClick={()=>onSelect(x)}><i style={{background:riskColor(x.resilience_score)}}/><div><b>{x.complex_name}</b><span>{x.address}</span></div><strong>{fmt(x.resilience_score)}</strong></button>)}</div></Page>; }

function RiskFeed({predictions,complexes}:{predictions:Prediction[];complexes:Complex[]}) { const names=Object.fromEntries(complexes.map(x=>[x.complex_id,x.complex_name])); return <Page title="AI 재난 위험 피드" subtitle="실데이터 기반 운영 선별 결과입니다. ML 발생확률과 구분해 표시합니다."><section className="panel">{predictions.length?<div className="risk-list">{predictions.map(x=><div className="risk-row" key={x.prediction_id}><TriangleAlert/><div><b>{names[x.complex_id]||x.complex_id}</b><span>{x.risk_type} · {x.model_version}</span></div><strong>{fmt(x.risk_probability*100)}</strong></div>)}</div>:<Empty text="현재 운영 선별 결과가 없습니다."/>}</section></Page>; }

function AiChat({complexes}:{complexes:Complex[]}) { const [target,setTarget]=useState(""); const [input,setInput]=useState(""); const [messages,setMessages]=useState<{role:string;text:string}[]>([]); const [busy,setBusy]=useState(false); const submit=async()=>{if(!input.trim())return;const q=input;setInput("");setMessages(m=>[...m,{role:"user",text:q}]);setBusy(true);try{const r=await api<any>("/api/v1/ai/chat",{method:"POST",body:JSON.stringify({question:q,complex_id:target||null})});setMessages(m=>[...m,{role:"ai",text:r.answer}]);}catch(e:any){setMessages(m=>[...m,{role:"ai",text:`오류: ${e.message}`}]);}finally{setBusy(false)}};return <Page title="AI 안전 관제" subtitle="Claude가 운영 DB의 검증 근거를 바탕으로 답변합니다."><section className="panel chat"><select value={target} onChange={e=>setTarget(e.target.value)}><option value="">전체 단지</option>{complexes.map(x=><option value={x.complex_id} key={x.complex_id}>{x.complex_name}</option>)}</select><div className="messages">{messages.length?messages.map((m,i)=><div className={m.role} key={i}>{m.text}</div>):<Empty text="질문을 입력하면 근거 기반 답변이 표시됩니다."/>}</div><div className="chat-input"><input value={input} onChange={e=>setInput(e.target.value)} onKeyDown={e=>e.key==="Enter"&&submit()} placeholder="안전·침수·시설 관련 질문"/><button onClick={submit} disabled={busy}><Send/></button></div></section></Page>; }

function Reports({complexes}:{complexes:Complex[]}) { const [target,setTarget]=useState(""); const [created,setCreated]=useState<any>(null); const [busy,setBusy]=useState(false); const create=async()=>{setBusy(true);try{setCreated(await api<any>("/api/v1/reports",{method:"POST",body:JSON.stringify({report_type:"comprehensive",complex_id:target||null})}));}finally{setBusy(false)}};return <Page title="AI 회복력 보고서" subtitle="현재 운영 DB 스냅샷으로 근거 보고서를 생성합니다."><section className="panel form-panel"><select value={target} onChange={e=>setTarget(e.target.value)}><option value="">서울 종합</option>{complexes.map(x=><option value={x.complex_id} key={x.complex_id}>{x.complex_name}</option>)}</select><button className="primary" onClick={create} disabled={busy}>{busy?"생성 중…":"보고서 생성"}</button>{created&&<a className="download" href={created.download_url}>생성된 보고서 다운로드</a>}</section></Page>; }
function DataManagement({quality,hydrology}:{quality:any;hydrology:any}) { const runs=quality?.collection_runs||[]; const configured=Object.entries(hydrology?.configuration||{}); const available=Object.entries(hydrology?.availability||{}); return <Page title="데이터 관리" subtitle="API 설정과 실제 적재 데이터 상태를 구분해 확인합니다."><div className="kpi-grid"><Kpi icon={<Database/>} label="전체 단지" value={quality?.complex_count||0} color="#2575eb"/><Kpi icon={<CheckCircle2/>} label="API 수집 준비" value={configured.filter(([,v]:any)=>v.collection_ready).length} color="#22a06b"/><Kpi icon={<Database/>} label="적재 데이터" value={available.filter(([,v]:any)=>v.status==="AVAILABLE").length} color="#2575eb"/><Kpi icon={<XCircle/>} label="확인 필요" value={available.filter(([,v]:any)=>v.status!=="AVAILABLE").length} color="#e5484d"/></div><section className="panel"><div className="panel-head"><h2>API 연결 설정</h2><span>키 값은 브라우저에 노출하지 않습니다</span></div><div className="source-grid">{configured.map(([name,value]:any)=><div className="source-card" key={name}><span className={`source-dot ${value.collection_ready?"ready":"blocked"}`}/><div><b>{name}</b><small>{value.collection_ready?"키·URL 설정 완료":"키 또는 URL 확인 필요"}</small></div></div>)}</div></section><section className="panel"><div className="panel-head"><h2>파일/API 적재 상태</h2></div><div className="source-grid">{available.map(([name,value]:any)=><div className="source-card" key={name}><span className={`source-dot ${value.status==="AVAILABLE"?"ready":"blocked"}`}/><div><b>{name}</b><small>{value.status} · {value.file_count||0}개 파일</small></div></div>)}</div></section><section className="panel"><div className="data-runs">{runs.slice(0,30).map((x:any)=><div key={x.collection_run_id}><span className={`status ${x.status}`}>{x.status}</span><b>{x.dataset_id}</b><span>{x.record_count||0}건</span><small>{x.failure_reason||"검증 완료"}</small></div>)}</div></section></Page>; }
function SystemSettings({models}:{models:any}) { return <Page title="시스템 설정" subtitle="외부 서비스와 모델 운영 상태입니다."><section className="panel"><h2>모델 상태</h2><div className="data-runs">{(models?.items||[]).map((x:any)=><div key={x.model_id}><span className={`status ${x.status}`}>{x.status}</span><b>{x.model_name}</b><small>{x.status_reason}</small></div>)}</div></section><section className="panel help"><h2>지도 설정</h2><p>NAVER 지도 Client ID와 인증 방식은 프로젝트 <code>.env</code>에서 관리합니다. 비밀키는 브라우저로 전달하지 않습니다.</p></section></Page>; }
function Empty({text}:{text:string}) { return <div className="empty"><ShieldCheck/><b>{text}</b><span>데이터 상태를 확인하거나 새로고침하십시오.</span></div>; }
