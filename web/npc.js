// 걷기 모드의 행인(사람·동물): 도로 위에서 랜덤하게 걷거나 가만히 서 있는다.
// 4단계: 'wander'(산책) / 'stand'(서 있기). 구경하기·모여서 이야기하기·전화하기는 5단계에서 추가.
import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { clone } from "three/addons/utils/SkeletonUtils.js";

const CAST = [   // [파일, 키(m), 걷는 속도(m/s)]
  ...["male-b", "male-c", "male-d", "male-e", "female-a", "female-b", "female-c", "female-d"].map(n => [`assets/characters/character-${n}.glb`, 1.7, 1.25]),
  ["assets/animals/animal-dog.glb", 0.6, 1.1], ["assets/animals/animal-cat.glb", 0.35, 0.9], ["assets/animals/animal-fox.glb", 0.55, 1.0],
  ["assets/animals/animal-bunny.glb", 0.4, 0.8], ["assets/animals/animal-pig.glb", 0.6, 0.7], ["assets/animals/animal-panda.glb", 0.9, 0.7],
];
const rng = (() => { let a = 20260101; return () => { a = (a + 0x6D2B79F5) | 0; let t = Math.imul(a ^ a >>> 15, 1 | a); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; }; })();
const rand = (a, b) => a + rng() * (b - a);
const npcs = []; let started = false;

function pickSpot(W) {   // 도로 필지 안에서 건물에 안 걸리는 점
  const { bbox, free } = W;
  for (let i = 0; i < 400; i++) { const p = [rand(bbox[0], bbox[2]), rand(bbox[1], bbox[3])]; if (free(p[0], p[1])) return p; }
  return null;
}

function setAnim(n, name) {
  const next = n.actions[name]; if (!next || next === n.cur) return;
  next.reset().play(); if (n.cur) n.cur.crossFadeTo(next, 0.25, false); n.cur = next;
}

function think(n, W) {   // 다음 행동 고르기
  if (n.mode === "wander" && rng() < 0.5) { n.mode = "stand"; n.timer = rand(3, 10); setAnim(n, "idle"); return; }
  for (let i = 0; i < 8; i++) {   // 6~20m 앞의 갈 수 있는 곳
    const a = rand(0, Math.PI * 2), d = rand(6, 20), tx = n.pos[0] + Math.sin(a) * d / W.KX, ty = n.pos[1] + Math.cos(a) * d / W.KY;
    let ok = true; for (let k = 1; k <= 6 && ok; k++) ok = W.free(n.pos[0] + (tx - n.pos[0]) * k / 6, n.pos[1] + (ty - n.pos[1]) * k / 6);
    if (ok) { n.mode = "wander"; n.target = [tx, ty]; setAnim(n, "walk"); return; }
  }
  n.mode = "stand"; n.timer = rand(2, 5); setAnim(n, "idle");
}

function update(dt, W) {
  for (const n of npcs) {
    if (n.mode === "stand") { n.timer -= dt; if (n.timer <= 0) think(n, W); }
    else {   // wander
      const dx = (n.target[0] - n.pos[0]) * W.KX, dy = (n.target[1] - n.pos[1]) * W.KY, dist = Math.hypot(dx, dy);
      if (dist < 0.3) think(n, W);
      else {
        const want = Math.atan2(dx, dy) * 180 / Math.PI, diff = ((want - n.heading + 540) % 360) - 180;
        n.heading = (n.heading + diff * Math.min(1, dt * 8) + 360) % 360;
        if (Math.abs(diff) < 50) {   // 방향이 어느 정도 맞은 뒤에 걷는다
          const st = Math.min(n.speed * dt, dist), nx = n.pos[0] + dx / dist * st / W.KX, ny = n.pos[1] + dy / dist * st / W.KY;
          if (W.free(nx, ny)) n.pos = [nx, ny]; else { n.mode = "stand"; n.timer = rand(1, 3); setAnim(n, "idle"); }   // 건물·도로 끝에 막힘
        }
      }
    }
    const l = window.Avatar.local(n.pos[0], n.pos[1]);
    n.obj.position.set(l.x, 0, l.z);
    n.obj.rotation.y = Math.PI - n.heading * Math.PI / 180;
    n.mixer.update(dt);
  }
}

async function start() {
  const W = window.NpcWorld; if (!W || started) return; started = true;
  const loader = new GLTFLoader(), cache = {};
  const load = url => cache[url] ||= new Promise((res, rej) => loader.load(url, res, undefined, rej));
  for (const [url, h, speed] of CAST) {
    const spot = pickSpot(W); if (!spot) continue;
    let gltf; try { gltf = await load(url); } catch (e) { console.error("NPC 모델 실패", url, e); continue; }
    const model = clone(gltf.scene);
    model.scale.setScalar(h / new THREE.Box3().setFromObject(model).getSize(new THREE.Vector3()).y);
    const obj = new THREE.Group(); obj.add(model); window.Avatar.scene.add(obj);
    const mixer = new THREE.AnimationMixer(model), actions = {};
    ["idle", "walk"].forEach(k => { const c = THREE.AnimationClip.findByName(gltf.animations, k); if (c) actions[k] = mixer.clipAction(c); });
    const n = { obj, mixer, actions, cur: null, pos: spot, heading: rand(0, 360), speed, mode: "stand", timer: rand(0, 4), target: null };
    setAnim(n, "idle"); mixer.update(rand(0, 2)); npcs.push(n);
  }
}

window.Avatar.addUpdater(dt => {
  if (!started) { if (window.Avatar.local(0, 0)) start(); return; }   // 기준점이 생긴 뒤(걷기 모드 첫 진입)에 소환
  update(dt, window.NpcWorld);
});
