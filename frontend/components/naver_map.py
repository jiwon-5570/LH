import json
import os
from pathlib import Path

import streamlit as st

_NAVER_MAP_COMPONENT = st.components.v2.component(
    "lh_predict_naver_map",
    html='<div class="map-shell"><div class="map-status">NAVER 지도 연결 중...</div><div class="map-canvas"></div></div>',
    css="""
.map-shell { position:relative; width:100%; height:100%; min-height:360px; overflow:hidden; border-radius:10px; background:#eef3f8; }
.map-canvas { width:100%; height:100%; min-height:360px; }
.map-status { position:absolute; z-index:10; left:14px; top:14px; padding:9px 12px; border-radius:8px; background:rgba(7,28,56,.9); color:white; font:12px sans-serif; box-shadow:0 3px 12px rgba(0,0,0,.18); }
""",
    js="""
export default function(component) {
  const { data, parentElement } = component;
  const mapElement = parentElement.querySelector('.map-canvas');
  const statusElement = parentElement.querySelector('.map-status');
  let disposed = false;
  let map = null;

  const fail = (message) => {
    if (!statusElement) return;
    statusElement.textContent = message;
    statusElement.style.background = '#b42318';
  };
  const loadSdk = () => {
    if (window.naver && window.naver.maps) return Promise.resolve();
    const sdkUrl = 'https://oapi.map.naver.com/openapi/v3/maps.js?' + data.authParam + '=' + encodeURIComponent(data.clientId);
    if (window.__lhPredictNaverSdkPromise && window.__lhPredictNaverSdkUrl === sdkUrl) return window.__lhPredictNaverSdkPromise;
    window.__lhPredictNaverSdkUrl = sdkUrl;
    window.__lhPredictNaverSdkPromise = new Promise((resolve, reject) => {
      const script = document.createElement('script');
      script.src = sdkUrl;
      script.async = true;
      script.onload = resolve;
      script.onerror = () => reject(new Error('SDK request failed'));
      document.head.appendChild(script);
    });
    return window.__lhPredictNaverSdkPromise;
  };

  loadSdk().then(() => {
    if (disposed || !mapElement || !window.naver?.maps) return;
    map = new window.naver.maps.Map(mapElement, {
      center: new window.naver.maps.LatLng(37.52, 126.98), zoom: 10,
      mapTypeControl: true, zoomControl: true,
      zoomControlOptions: { position: window.naver.maps.Position.TOP_RIGHT }
    });
    (data.demTiles || []).forEach(tile => {
      const polygon = new window.naver.maps.Polygon({
        map, paths: tile.polygon.map(p => new window.naver.maps.LatLng(p[0], p[1])),
        fillColor:'#1768e5', fillOpacity:.13, strokeColor:'#1768e5', strokeOpacity:.9, strokeWeight:2, clickable:true
      });
      window.naver.maps.Event.addListener(polygon, 'click', () => alert('국토지리정보원 DEM: ' + tile.tile));
    });
    const scoreColor = (score) => score == null ? '#8b98a9' : score <= 39 ? '#e53935' : score <= 59 ? '#fb8c00' : score <= 74 ? '#f6c945' : '#35b987';
    (data.rows || []).forEach(row => {
      const color = scoreColor(row.resilience_score);
      const marker = new window.naver.maps.Marker({
        map, position:new window.naver.maps.LatLng(row.latitude,row.longitude), title:row.complex_name || '',
        icon:{content:`<div style="width:24px;height:24px;border-radius:50% 50% 50% 0;transform:rotate(-45deg);background:${color};border:2px solid white;box-shadow:0 2px 7px #0005"><span style="display:block;transform:rotate(45deg);color:white;text-align:center;font:bold 11px/20px sans-serif">LH</span></div>`,anchor:new window.naver.maps.Point(12,24)}
      });
      const value = (v, suffix='') => v == null ? '데이터 부족' : Number(v).toFixed(1) + suffix;
      const popup = new window.naver.maps.InfoWindow({content:`<div style="padding:13px 15px;min-width:240px;font:12px sans-serif;color:#17263a"><b style="font-size:14px">${row.complex_name || ''}</b><div style="color:#718096;margin:5px 0 9px">${row.address || ''}</div><div>회복력 <b style="color:${color}">${value(row.resilience_score,'점')}</b></div><div>데이터 신뢰도 <b>${value(row.data_confidence,'점')}</b></div><div style="color:#8793a5;margin-top:7px">분석 기준 ${row.assessed_at || '미분석'}</div></div>`});
      window.naver.maps.Event.addListener(marker, 'click', () => popup.getMap() ? popup.close() : popup.open(map, marker));
    });
    statusElement.textContent = 'NAVER · DEM ' + (data.demTiles || []).length + '개 · 단지 좌표 ' + (data.rows || []).length + '개';
    setTimeout(() => { if (!disposed && statusElement) statusElement.style.display='none'; }, 3500);
  }).catch(() => fail('NAVER Maps SDK 로드 실패'));

  return () => { disposed = true; map = null; };
}
""",
)


def _dem_coverage() -> list[dict]:
    try:
        from pyproj import Transformer

        transformer = Transformer.from_crs("EPSG:5179", "EPSG:4326", always_xy=True)
        coverage = []
        for path in Path("data/processed/ngii_dem").glob("*_raster_metadata.json"):
            metadata = json.loads(path.read_text(encoding="utf-8"))
            left, bottom, right, top = metadata["bounds"]
            west, south = transformer.transform(left, bottom)
            east, north = transformer.transform(right, top)
            coverage.append({
                "tile": metadata.get("source_file", path.stem),
                "polygon": [[south, west], [south, east], [north, east], [north, west]],
            })
        return coverage
    except (OSError, ValueError, KeyError, json.JSONDecodeError):
        return []


def render_naver_map(items: list[dict], height: int = 520):
    client_id = os.getenv("NAVER_MAP_CLIENT_ID", "").strip()
    auth_param = os.getenv("NAVER_MAP_AUTH_PARAM", "ncpKeyId").strip()
    if auth_param not in {"ncpKeyId", "ncpClientId"}:
        auth_param = "ncpKeyId"
    if not client_id:
        st.error("NAVER_MAP_CLIENT_ID가 설정되지 않았습니다. 시스템 설정에서 입력하십시오.")
        return

    valid = [x for x in items if x.get("latitude") is not None and x.get("longitude") is not None]
    _NAVER_MAP_COMPONENT(
        data={"clientId": client_id, "authParam": auth_param, "rows": valid, "demTiles": _dem_coverage()},
        key="lh-predict-naver-map",
        width="stretch",
        height=height,
    )
    if not valid:
        st.caption("NAVER 지도에 DEM 4개 범위를 표시 중입니다. LH 단지 데이터에는 좌표가 없어 단지 마커는 아직 표시되지 않습니다.")
