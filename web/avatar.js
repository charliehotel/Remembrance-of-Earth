// 걷기 모드 캐릭터: MapLibre 커스텀 레이어 위에 three.js로 Kenney glb 캐릭터를 그린다.
// 메인 스크립트(index.html)는 window.Avatar.set(pos, heading) / setVisible(on)만 부른다.
import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";

const MODEL_URL = "assets/characters/character-male-a.glb";
const HEIGHT_M = 1.7;   // 캐릭터 키(m)

const state = { map: null, pos: null, heading: 0, visible: false, ready: false };
let renderer, scene, camera, origin, mPerUnit, avatar, mixer;
const actions = {}; let current = null, wanted = "idle";
const clock = new THREE.Clock();

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
    mixer.update(clock.getDelta());
    const s = mPerUnit;
    const l = new THREE.Matrix4().makeTranslation(origin.x, origin.y, 0)
      .scale(new THREE.Vector3(s, -s, s))
      .multiply(new THREE.Matrix4().makeRotationX(Math.PI / 2));
    camera.projectionMatrix = new THREE.Matrix4().fromArray(matrix).multiply(l);
    renderer.resetState();
    renderer.render(scene, camera);
    state.map.triggerRepaint();   // 애니메이션을 계속 돌린다
  },
};

window.Avatar = {
  isReady: () => state.ready,
  set(pos, heading, anim = "idle") {   // heading = 캐릭터가 바라보는 방위, anim = idle | walk | sprint
    state.pos = pos; state.heading = heading; wanted = anim; play(anim);
    placeAvatar(); state.map?.triggerRepaint();
  },
  setVisible(on) { state.visible = on; if (avatar) avatar.visible = on; state.map?.triggerRepaint(); },
};

function attach(map) { state.map = map; map.addLayer(layer); }
if (window.__mapReady) attach(window.__map);
else window.addEventListener("map-ready", () => attach(window.__map), { once: true });
