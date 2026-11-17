// 경의중앙선 철도 둑(창천교회 북쪽) 위를 오가는 열차. scripts/build_rail.py 의 선로(y = 47 + 0.04x, 선로면 10.5m)를 따라 달린다.
//  - 동행(신촌역 방향): 남쪽 선로. 서쪽 끝에서 들어와 쉬지 않고 동쪽 끝으로 빠져나간다.
//  - 서행(반대 방향): 북쪽 선로. 동쪽 끝에서 들어와 서쪽 끝으로 빠져나간다.
//  신촌역은 창천교회 반경 300m 밖이라 지도에 없으므로 정차하지 않는다.
//  - 방향마다 한 편성씩만 다닌다. 출발 간격은 무작위.
// 열차는 MapLibre fill-extrusion 레이어('trains')로 그리고, 프레임마다 GeoJSON 을 갱신한다(차량 7~8량 x 7조각).
const C0 = 126.93756304043873, C1 = 37.55915909082795;          // build_rail.py 의 지역 좌표 원점(교회 필지 중심)
const KX = 111320 * Math.cos(37.559 * Math.PI / 180), KY = 110540;
const cy = x => 47 + 0.04 * x;                                   // 둑 중심선
const NX = -0.04 / Math.hypot(1, 0.04), NY = 1 / Math.hypot(1, 0.04);   // 선로에 수직인 단위 벡터(북쪽 쪽)
const X0 = -200, X1 = 250;                                       // 선로가 그려진 구간(m)
const LANE = { east: -4.2, west: 4.2 };                          // 중심선에서 떨어진 정도(우측통행: 동행은 남쪽)
const CAR_L = 19.5, GAP = 0.5, CAR_W = 3.1, DECK = 10.75;
const VARIANTS = [
  { body: "#e8ebed", stripe: "#4fb3a5", win: "#27323c", door: "#aab3ba" },   // 경의중앙선(은백색 + 청록 띠)
  { body: "#e8ebed", stripe: "#4fb3a5", win: "#27323c", door: "#aab3ba" },
  { body: "#d4dce3", stripe: "#2a5aa8", win: "#202b36", door: "#8e9aa5" },   // 다른 계열 열차(파랑 띠)
];

const ll = (x, y) => [C0 + x / KX, C1 + y / KY];
function quad(xa, xb, off, hw) {                                 // x∈[xa,xb] 구간, 선로 off, 반폭 hw 인 직사각형(폐곡선)
  const ya = cy(xa) + off, yb = cy(xb) + off;
  return [ll(xa + NX * hw, ya + NY * hw), ll(xb + NX * hw, yb + NY * hw), ll(xb - NX * hw, yb - NY * hw), ll(xa - NX * hw, ya - NY * hw), ll(xa + NX * hw, ya + NY * hw)];
}
const feat = (ring, b, h, c) => ({ type: "Feature", properties: { b, h, c }, geometry: { type: "Polygon", coordinates: [ring] } });

function carFeatures(t, k, out) {
  const d = t.dir, Lc = CAR_L, step = CAR_L + GAP;
  const f0 = t.head - d * k * step, f1 = f0 - d * Lc;              // 앞끝·뒤끝 x
  const lo = Math.max(Math.min(f0, f1), X0), hi = Math.min(Math.max(f0, f1), X1);
  if (hi - lo < 0.6) return;                                       // 구간 밖이면 그리지 않는다(가장자리에서 서서히 나타나고 사라진다)
  const v = t.v, off = t.off, hw = CAR_W / 2;
  out.push(feat(quad(lo, hi, off, hw - 0.15), DECK, DECK + 0.5, "#3d4044"));          // 대차·하부
  out.push(feat(quad(lo, hi, off, hw), DECK + 0.5, DECK + 3.4, v.body));               // 차체
  out.push(feat(quad(lo, hi, off, hw + 0.03), DECK + 0.6, DECK + 1.0, v.stripe));      // 하단 색 띠
  out.push(feat(quad(lo, hi, off, hw + 0.03), DECK + 1.5, DECK + 2.6, v.win));         // 창
  for (const r of [0.14, 0.5, 0.86]) {                                                  // 출입문 3쌍
    const c = Math.min(f0, f1) + (d > 0 ? r : 1 - r) * Lc;
    const a = Math.max(c - 0.7, lo), b = Math.min(c + 0.7, hi);
    if (b - a > 0.2) out.push(feat(quad(a, b, off, hw + 0.06), DECK + 0.6, DECK + 2.9, v.door));
  }
  if (k === 0 || k === t.n - 1) {                                                       // 맨 앞(진행 방향)·맨 뒤 운전실 앞유리
    const front = k === 0;
    const e = front ? f0 : f1, dir = front ? d : -d;
    const a = Math.min(e, e + dir * 0.06), b = Math.max(e, e + dir * 0.06);
    if (b > X0 && a < X1) out.push(feat(quad(Math.max(a, X0), Math.min(b, X1), off, hw - 0.5), DECK + 1.3, DECK + 2.7, front ? "#1a2028" : "#454b52"));
  }
}

const trains = [];
let nextSpawn = 0, last = 0, acc = 0;
const rnd = (a, b) => a + Math.random() * (b - a);

function spawn(dirName, now) {
  const n = 6 + Math.floor(Math.random() * 3);                   // 6~8량
  const v = VARIANTS[Math.floor(Math.random() * VARIANTS.length)];
  const len = n * (CAR_L + GAP) - GAP;
  const east = dirName === "east";
  const cruise = rnd(14, 20);
  const t = { dirName, dir: east ? 1 : -1, off: LANE[dirName], n, len, v, speed: cruise,
              head: east ? X0 : X1 + 4 };                            // 동행은 서쪽 끝에서, 서행은 동쪽 끝 바깥에서 들어온다
  trains.push(t);
  return t;
}

function step(t, dt) {
  t.head += t.dir * t.speed * dt;
}
const gone = t => t.dirName === "east" ? t.head - t.len > X1 + 5 : t.head + t.len < X0 - 5;

function frame(map, ts) {
  requestAnimationFrame(t2 => frame(map, t2));
  if (document.hidden) { last = 0; return; }
  const now = ts / 1000;
  if (!last) last = now;
  const dt = Math.min(0.25, now - last);
  last = now; acc += dt;
  if (acc < 0.1) return;                                          // 10 fps 로 갱신(건물 소스와 MapLibre 워커를 같이 쓰므로 과하게 보내지 않는다)
  const h = acc; acc = 0;
  for (const t of trains) step(t, h);
  for (let i = trains.length - 1; i >= 0; i--) if (gone(trains[i])) trains.splice(i, 1);
  if (now >= nextSpawn) {                                         // 방향마다 한 편성씩. 출발 간격은 무작위
    const free = ["east", "west"].filter(d => !trains.some(t => t.dirName === d));
    if (free.length) { spawn(free[Math.floor(Math.random() * free.length)], now); nextSpawn = now + rnd(6, 20); }
    else nextSpawn = now + 2;
  }
  const feats = [];
  for (const t of trains) for (let k = 0; k < t.n; k++) carFeatures(t, k, feats);
  map.getSource("trains")?.setData({ type: "FeatureCollection", features: feats });
}

function attach(map) {
  if (!map.getSource("rail")) return;                             // 철도 둑 데이터가 없으면 열차도 없다
  map.addSource("trains", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
  const before = map.getLayer("ctx-bld-x") ? "ctx-bld-x" : undefined;
  map.addLayer({ id: "trains", type: "fill-extrusion", source: "trains", paint: {
    "fill-extrusion-color": ["get", "c"], "fill-extrusion-base": ["get", "b"], "fill-extrusion-height": ["get", "h"], "fill-extrusion-opacity": 1 } }, before);
  const t0 = spawn("east", 0);                                    // 처음부터 선로 가운데를 달리는 열차가 한 편성 있다
  t0.head = rnd(-20, 120);
  nextSpawn = performance.now() / 1000 + rnd(3, 8);
  requestAnimationFrame(ts => frame(map, ts));
}
if (window.__mapReady) attach(window.__map);
else window.addEventListener("map-ready", () => attach(window.__map), { once: true });
