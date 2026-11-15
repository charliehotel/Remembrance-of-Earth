// 걷기 모드 캐릭터: MapLibre 커스텀 레이어 위에 three.js로 Kenney glb 캐릭터를 그린다.
// 메인 스크립트(index.html)는 window.Avatar.set(pos, heading) / setVisible(on)만 부른다.
import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";

const MODEL_URL = "assets/characters/character-male-a.glb";
const HEIGHT_M = 1.7;   // 캐릭터 키(m)

const state = { map: null, pos: null, heading: 0, visible: false, ready: false };
let renderer, scene, camera, origin, mPerUnit, avatar, mixer;
const actions = {}; let current = null, wanted = "idle";
const clock = new THREE.Clock(), updaters = [];

// three 좌표계: x = 동, y = 위, z = 남. 단위는 m. 원점은 처음 캐릭터를 둔 자리.
function placeAvatar() {
  if (!avatar || !state.pos) return;
  if (!origin) { origin = maplibregl.MercatorCoordinate.fromLngLat(state.pos, 0); mPerUnit = origin.meterInMercatorCoordinateUnits(); }
  const m = maplibregl.MercatorCoordinate.fromLngLat(state.pos, 0);
  avatar.position.set((m.x - origin.x) / mPerUnit, 0, (m.y - origin.y) / mPerUnit);
  avatar.rotation.y = Math.PI - state.heading * Math.PI / 180;   // 모델 정면(+z)을 헤딩(북=0, 시계방향)으로
}

function play(name, fade = 0.2) {   // 동작을 부드럽게 바꾼다
  const next = actions[name]; if (!next || next === current) return;
  next.reset().play(); if (current) current.crossFadeTo(next, fade, false); current = next;
}

const layer = {
  id: "avatar3d", type: "custom", renderingMode: "3d",
  onAdd(map, gl) {
    camera = new THREE.Camera(); scene = new THREE.Scene();
    scene.add(new THREE.HemisphereLight(0xffffff, 0x8a8577, 2.2));
    const sun = new THREE.DirectionalLight(0xffffff, 1.6); sun.position.set(-30, 60, 20); scene.add(sun);
    renderer = new THREE.WebGLRenderer({ canvas: map.getCanvas(), context: gl, antialias: true });
    renderer.autoClear = false;
    new GLTFLoader().load(MODEL_URL, gltf => {
      const model = gltf.scene;
      const size = new THREE.Box3().setFromObject(model).getSize(new THREE.Vector3());
      model.scale.setScalar(HEIGHT_M / size.y);
      avatar = new THREE.Group(); avatar.add(model); avatar.visible = state.visible; scene.add(avatar);
      mixer = new THREE.AnimationMixer(model);
      ["idle", "walk", "sprint"].forEach(n => { const c = THREE.AnimationClip.findByName(gltf.animations, n); if (c) actions[n] = mixer.clipAction(c); });
      play(wanted, 0);
      state.ready = true; placeAvatar();
      window.dispatchEvent(new Event("avatar-ready"));
      map.triggerRepaint();
    }, undefined, err => console.error("캐릭터 모델을 불러오지 못했다", err));
  },
  render(gl, matrix) {
    if (!avatar || !origin || !state.visible) return;
    const dt = Math.min(clock.getDelta(), 0.1);
    mixer.update(dt); updaters.forEach(f => f(dt));
    const s = mPerUnit;
    const l = new THREE.Matrix4().makeTranslation(origin.x, origin.y, 0)
      .scale(new THREE.Vector3(s, -s, s))
      .multiply(new THREE.Matrix4().makeRotationX(Math.PI / 2));
    camera.projectionMatrix = new THREE.Matrix4().fromArray(matrix).multiply(l);
    renderer.resetState();
    // 1) 행인: 건물과 깊이를 비교해서 그린다(건물 뒤에 있으면 가려진다)
    avatar.visible = false;
    renderer.render(scene, camera);
    // 2) 내 캐릭터: 반투명 건물도 깊이를 쓰기 때문에, 깊이를 비우고 위에 그린다(행인은 이 패스에서 제외)
    const hidden = scene.children.filter(o => o !== avatar && !o.isLight && o.visible);
    hidden.forEach(o => o.visible = false); avatar.visible = true;
    renderer.clearDepth();
    renderer.render(scene, camera);
    hidden.forEach(o => o.visible = true);
    state.map.triggerRepaint();   // 애니메이션을 계속 돌린다
  },
};

window.Avatar = {
  isReady: () => state.ready,
  get scene() { return scene; },
  addUpdater: f => updaters.push(f),                       // 매 프레임 f(dt) 호출(걷기 모드가 켜져 있을 때)
  local(lng, lat) {                                        // 경위도 -> three 좌표(m). 아직 기준점이 없으면 null
    if (!origin) return null;
    const m = maplibregl.MercatorCoordinate.fromLngLat([lng, lat], 0);
    return { x: (m.x - origin.x) / mPerUnit, z: (m.y - origin.y) / mPerUnit };
  },
  set(pos, heading, anim = "idle") {   // heading = 캐릭터가 바라보는 방위, anim = idle | walk | sprint
    state.pos = pos; state.heading = heading; wanted = anim; play(anim);
    placeAvatar(); state.map?.triggerRepaint();
  },
  setVisible(on) { state.visible = on; if (avatar) avatar.visible = on; state.map?.triggerRepaint(); },
  held: () => heldApi ||= createHeld(),   // 커서에 매달린 작은 캐릭터(처음 부를 때 만든다)
};

// ---- 커서에 매달린 작은 캐릭터: 걷기 모드를 시작하기 전에 놓을 자리를 고를 때 쓴다 ----
// 지도와 별개의 작은 캔버스에 같은 모델(fall 동작)을 그리고, CSS 로 커서 위치에 붙인 뒤 진자처럼 흔든다.
// 쓰는 쪽: const h = Avatar.held(); h.show(x, y); h.move(x, y); h.setValid(true|false); h.hide(dropped)
let heldApi = null;
function createHeld() {
  const W = 32, H = 44, PIVOT_UP = 3;   // PIVOT_UP: 커서 끝이 캐릭터 머리 위 몇 px 에 오게 할지
  const cv = document.createElement("canvas");
  Object.assign(cv.style, { position: "fixed", left: "0", top: "0", marginLeft: -W / 2 + "px", width: W + "px", height: H + "px",
    pointerEvents: "none", zIndex: "30", display: "none", transformOrigin: "50% 0", transition: "opacity .15s, filter .15s" });
  document.body.appendChild(cv);
  const r = new THREE.WebGLRenderer({ canvas: cv, alpha: true, antialias: true });
  r.setPixelRatio(Math.min(devicePixelRatio || 1, 2)); r.setSize(W, H, false); r.setClearColor(0x000000, 0);
  const sc = new THREE.Scene(), cam = new THREE.PerspectiveCamera(24, W / H, 0.1, 50);
  cam.position.set(0, 0.92, 5); cam.lookAt(0, 0.92, 0);
  sc.add(new THREE.HemisphereLight(0xffffff, 0x8a8577, 2.4));
  const sun = new THREE.DirectionalLight(0xffffff, 1.6); sun.position.set(-2, 4, 5); sc.add(sun);
  let mixer = null;
  new GLTFLoader().load(MODEL_URL, gltf => {
    const model = gltf.scene, size = new THREE.Box3().setFromObject(model).getSize(new THREE.Vector3());
    model.scale.setScalar(HEIGHT_M / size.y); sc.add(model);
    mixer = new THREE.AnimationMixer(model);
    const clip = THREE.AnimationClip.findByName(gltf.animations, "fall") || THREE.AnimationClip.findByName(gltf.animations, "idle");
    if (clip) mixer.clipAction(clip).play();
  }, undefined, err => console.error("커서용 캐릭터 모델을 불러오지 못했다", err));

  let x = 0, y = 0, ang = 0, vel = 0, on = false, raf = 0, last = 0, hideTimer = 0;
  const place = () => { cv.style.transform = `translate(${x}px, ${y - PIVOT_UP}px) rotate(${ang}deg)`; };
  function tick(t) {
    if (!on) return;
    const dt = Math.min((t - last) / 1000, 0.05); last = t;
    vel += (-90 * ang - 4.5 * vel) * dt; ang = Math.max(-50, Math.min(50, ang + vel * dt));   // 용수철-감쇠 진자
    place(); if (mixer) mixer.update(dt); r.render(sc, cam);
    raf = requestAnimationFrame(tick);
  }
  return {
    show(px, py) {
      clearTimeout(hideTimer); x = px; y = py; ang = vel = 0; on = true;
      cv.style.display = "block"; cv.style.transition = "opacity .15s, filter .15s"; cv.style.opacity = "1"; cv.style.scale = "1"; place();
      last = performance.now(); cancelAnimationFrame(raf); raf = requestAnimationFrame(tick);
    },
    move(px, py) { if (!on) return; vel = Math.max(-700, Math.min(700, vel + (px - x) * 2.2)); x = px; y = py; place(); },   // 커서가 오른쪽으로 가면 몸은 왼쪽으로 처진다
    setValid(v) { cv.style.opacity = v ? "1" : "0.5"; cv.style.filter = v ? "drop-shadow(0 2px 2px rgba(0,0,0,.35))" : "grayscale(1)"; },
    hide(dropped) {   // dropped: 내려놓는 중이면 작아지며 사라진다
      on = false; cancelAnimationFrame(raf);
      cv.style.transition = "opacity .18s, scale .18s"; cv.style.opacity = "0"; if (dropped) cv.style.scale = "0.6";
      hideTimer = setTimeout(() => { cv.style.display = "none"; }, 200);
    },
  };
}

function attach(map) { state.map = map; map.addLayer(layer); }
if (window.__mapReady) attach(window.__map);
else window.addEventListener("map-ready", () => attach(window.__map), { once: true });
