import { useEffect, useRef, useState } from "react";
import type { Complex } from "./api";
import { fmt, riskColor } from "./api";

declare global { interface Window { naver?: any; __naverMapPromise?: Promise<void>; } }

type Config = { naver_map_client_id: string; naver_map_auth_param: string };

function appendSdk(clientId: string, authParam: string) {
  return new Promise<void>((resolve, reject) => {
    const script = document.createElement("script");
    script.dataset.lhNaverMap = "true";
    script.src = `https://oapi.map.naver.com/openapi/v3/maps.js?${authParam}=${encodeURIComponent(clientId)}`;
    script.onload = () => window.naver?.maps ? resolve() : reject(new Error("NAVER Maps SDK가 지도 객체를 반환하지 않았습니다."));
    script.onerror = () => { script.remove(); reject(new Error(`NAVER Maps SDK 인증 실패 (${authParam})`)); };
    document.head.appendChild(script);
  });
}

function loadSdk(config: Config) {
  if (window.naver?.maps) return Promise.resolve();
  if (window.__naverMapPromise) return window.__naverMapPromise;
  const primary = config.naver_map_auth_param || "ncpKeyId";
  const fallback = primary === "ncpKeyId" ? "ncpClientId" : "ncpKeyId";
  window.__naverMapPromise = appendSdk(config.naver_map_client_id, primary)
    .catch(() => appendSdk(config.naver_map_client_id, fallback))
    .catch(() => {
      window.__naverMapPromise = undefined;
      throw new Error(`NAVER 지도 인증 실패: 네이버 콘솔 Web 서비스 URL에 ${location.origin} 을 등록하세요.`);
    });
  return window.__naverMapPromise;
}

export function NaverMap({ rows, onSelect }: { rows: Complex[]; onSelect: (item: Complex) => void }) {
  const element = useRef<HTMLDivElement>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    setError("");
    fetch("/api/v1/frontend-config").then(r => {
      if (!r.ok) throw new Error(`지도 설정 조회 실패 (${r.status})`);
      return r.json();
    }).then((config: Config) => {
      if (!config.naver_map_client_id) throw new Error("NAVER_MAP_CLIENT_ID가 설정되지 않았습니다.");
      return loadSdk(config);
    }).then(() => {
      if (!active || !element.current) return;
      const naver = window.naver;
      const map = new naver.maps.Map(element.current, {
        center: new naver.maps.LatLng(37.53, 126.98), zoom: 11,
        zoomControl: true, mapTypeControl: true
      });
      rows.filter(x => x.latitude != null && x.longitude != null).forEach(row => {
        const color = riskColor(row.resilience_score);
        const marker = new naver.maps.Marker({
          map, position: new naver.maps.LatLng(row.latitude, row.longitude), title: row.complex_name,
          icon: { content: `<button class="map-pin" style="background:${color}">LH</button>`, anchor: new naver.maps.Point(16, 32) }
        });
        const info = new naver.maps.InfoWindow({ content: `<div class="map-popup"><b>${row.complex_name}</b><span>${row.address}</span><strong style="color:${color}">${fmt(row.resilience_score)}</strong></div>` });
        naver.maps.Event.addListener(marker, "click", () => { info.open(map, marker); onSelect(row); });
      });
    }).catch(e => active && setError(String(e.message || e)));
    return () => { active = false; };
  }, [rows, onSelect]);
  return <div className="map-wrap">{error && <div className="map-error">{error}</div>}<div className="map" ref={element} /></div>;
}
