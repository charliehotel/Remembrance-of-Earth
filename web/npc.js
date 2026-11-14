// 걷기 모드의 행인(사람·동물). 역할마다 행동이 다르다.
//  walker : 도로를 걷다가 서 있거나 건물을 구경한다
//  watcher: 건물을 올려다보며 구경하고, 가끔 다른 곳으로 옮겨 간다
//  caller : 서서 전화하고, 가끔 걸으면서 자리를 옮긴다
//  talker : 2~3명이 한 곳에 모여(gather) 마주 보고 이야기하다(talk), 다 같이 다른 곳으로 옮긴다
//  pet    : 동물. 걷다가 먹거나(eat) 춤춘다(dance)
import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { clone } from "three/addons/utils/SkeletonUtils.js";

const HUMANS = ["male-b", "male-c", "male-d", "male-e", "male-f", "male-g", "female-a", "female-b", "female-c", "female-d", "female-e", "female-f"];
let hi = 0; const human = () => `assets/characters/character-${HUMANS[hi++ % HUMANS.length]}.glb`;
const animal = (n, h, sp) => ({ url: `assets/animals/animal-${n}.glb`, h, speed: sp, role: "pet" });
const P = (role, group) => ({ url: human(), h: 1.7, speed: 1.25, role, group });
const SPECS = [
  P("walker"), P("walker"), P("walker"), P("walker"),
  P("watcher"), P("watcher"),
  P("caller"), P("caller"),
  P("talker", 0), P("talker", 0), P("talker", 0),   // 이야기 모임 A (3명)
  P("talker", 1), P("talker", 1),                   // 이야기 모임 B (2명)
  animal("dog", 0.6, 1.1), animal("fox", 0.55, 1.0), animal("cat", 0.35, 0.9),
  animal("bunny", 0.4, 0.8), animal("pig", 0.6, 0.7), animal("panda", 0.9, 0.7),
];
const CLIPS = ["idle", "walk", "holding-left", "interact-left", "interact-right", "emote-yes", "emote-no", "eat", "dance"];
const PHONE = ["holding-left", "interact-left"];   // 전화 자세로 쓸 동작(앞에서부터 있는 것). 화면에서 어색하면 이 순서를 바꾼다
const GESTURES = ["emote-yes", "emote-no", "interact-left", "interact-right"];

const rng = (() => { let a = 20260101; return () => { a = (a + 0x6D2B79F5) | 0; let t = Math.imul(a ^ a >>> 15, 1 | a); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; }; })();
const rand = (a, b) => a + rng() * (b - a);
const pick = arr => arr[Math.floor(rng() * arr.length)];
const npcs = [], groups = []; let started = false, clockT = 0;

const bearing = (n, p, W) => Math.atan2((p[0] - n.pos[0]) * W.KX, (p[1] - n.pos[1]) * W.KY) * 180 / Math.PI;
const dist = (n, p, W) => Math.hypot((p[0] - n.pos[0]) * W.KX, (p[1] - n.pos[1]) * W.KY);
const turnTo = (n, deg, dt, rate = 8) => { const d = ((deg - n.heading + 540) % 360) - 180; n.heading = (n.heading + d * Math.min(1, dt * rate) + 360) % 360; return Math.abs(d); };

function pickSpot(W, near, dmin = 0, dmax = 0) {   // 도로 위 빈 점. near가 있으면 그 주변 dmin~dmax m
  for (let i = 0; i < 400; i++) {
    let p;
    if (near) { const a = rand(0, Math.PI * 2), d = rand(dmin, dmax); p = [near[0] + Math.sin(a) * d / W.KX, near[1] + Math.cos(a) * d / W.KY]; }
    else p = [rand(W.bbox[0], W.bbox[2]), rand(W.bbox[1], W.bbox[3])];
    if (W.free(p[0], p[1])) return p;
  }
  return null;
}

function setAnim(n, name, once = false) {
  const next = n.actions[name]; if (!next) return;
  if (next === n.cur && !once) return;
  if (once) { next.setLoop(THREE.LoopOnce, 1); next.clampWhenFinished = true; } else { next.setLoop(THREE.LoopRepeat, Infinity); next.clampWhenFinished = false; }
  next.reset().play(); if (n.cur && n.cur !== next) n.cur.crossFadeTo(next, 0.25, false); n.cur = next;
}

function nearestBuilding(n, W) {   // 가장 가까운 건물 꼭짓점(40m 이내)
  let best = null, bd = 40;
  for (const f of W.buildings()) for (const q of f.geometry.coordinates[0]) { const d = dist(n, q, W); if (d < bd && d > 1.5) { bd = d; best = q; } }
  return best;
}

// ---- 행동 시작 ----
const startStand = (n, t = rand(3, 10)) => {
  n.mode = "stand"; n.timer = t;
  let a = "idle";
  if (n.role === "pet") { const r = rng(); a = r < 0.5 ? "eat" : r < 0.65 ? "dance" : "idle"; }
  setAnim(n, n.actions[a] ? a : "idle");
};
function startWatch(n, W) {
  const p = nearestBuilding(n, W); if (!p) return startStand(n);
  n.mode = "watch"; n.timer = rand(8, 18); n.look = p; n.phase = rand(0, 6.28); setAnim(n, "idle");
}
function startCall(n) {
  const a = PHONE.find(k => n.actions[k]); if (!a) return startStand(n);
  n.mode = "call"; n.timer = rand(15, 30); n.base = n.heading; n.phase = rand(0, 6.28); setAnim(n, a);
}
function startWalk(n, W, dmin = 6, dmax = 20) {   // 갈 수 있는 목표 찾기
  for (let i = 0; i < 8; i++) {
    const t = pickSpot(W, n.pos, dmin, dmax); if (!t) break;
    let ok = true; for (let k = 1; k <= 6 && ok; k++) ok = W.free(n.pos[0] + (t[0] - n.pos[0]) * k / 6, n.pos[1] + (t[1] - n.pos[1]) * k / 6);
    if (ok) { n.mode = "wander"; n.target = t; n.blocked = 0; setAnim(n, "walk"); return true; }
  }
  startStand(n, rand(2, 5)); return false;
}
function startTalk(n, W) {
  n.mode = "talk"; n.timer = 0; n.gt = rand(1, 5); setAnim(n, "idle");
}

function think(n, W) {   // 한 행동이 끝났을 때 다음 행동 고르기
  const was = n.mode;
  if (n.role === "caller") { if (was === "call") startWalk(n, W, 4, 10); else startCall(n); return; }
  if (n.role === "watcher") { if (was === "watch") startWalk(n, W, 8, 25); else startWatch(n, W); return; }
  const r = rng();   // walker, pet
  if (was === "wander") { if (r < 0.3 && n.role === "walker") startWatch(n, W); else if (r < 0.65) startStand(n); else startWalk(n, W); }
  else startWalk(n, W);
}

// ---- 이야기 모임 ----
function slotsFor(W, c, k) {
  const R = k === 2 ? 0.8 : 1.0, a0 = rand(0, 6.28), s = [];
  for (let i = 0; i < k; i++) { const a = a0 + i * 2 * Math.PI / k; s.push([c[0] + Math.sin(a) * R / W.KX, c[1] + Math.cos(a) * R / W.KY]); }
  return s.every(p => W.free(p[0], p[1])) ? s : null;
}
function newSite(g, W, near) {
  for (let i = 0; i < 80; i++) {
    const c = near ? pickSpot(W, near, 10, 25) : pickSpot(W); if (!c) continue;
    const s = slotsFor(W, c, g.members.length); if (s) { g.center = c; g.members.forEach((m, j) => { m.slot = s[j]; m.mode = "gather"; m.blocked = 0; setAnim(m, "walk"); }); return true; }
  }
  return false;
}

// ---- 이동 ----
function moveToward(n, t, speed, dt, W) {   // -> "arrived" | "blocked" | "moving"
  const dx = (t[0] - n.pos[0]) * W.KX, dy = (t[1] - n.pos[1]) * W.KY, d = Math.hypot(dx, dy);
  if (d < 0.25) return "arrived";
  const diff = turnTo(n, Math.atan2(dx, dy) * 180 / Math.PI, dt);
  if (diff >= 50) return "moving";   // 방향이 어느 정도 맞은 뒤에 걷는다
  const st = Math.min(speed * dt, d), nx = n.pos[0] + dx / d * st / W.KX, ny = n.pos[1] + dy / d * st / W.KY;
  if (W.free(nx, ny)) { n.pos = [nx, ny]; return "moving"; }
  return "blocked";
}

function update(dt, W) {
  clockT += dt;
  for (const n of npcs) {
    switch (n.mode) {
      case "stand": n.timer -= dt; if (n.timer <= 0) think(n, W); break;
      case "watch": {   // 건물 쪽을 보며 천천히 좌우로 둘러본다
        turnTo(n, bearing(n, n.look, W) + Math.sin(clockT * 0.5 + n.phase) * 28, dt, 3);
        n.timer -= dt; if (n.timer <= 0) think(n, W); break; }
      case "call":
        turnTo(n, n.base + Math.sin(clockT * 0.3 + n.phase) * 20, dt, 2);
        n.timer -= dt; if (n.timer <= 0) think(n, W); break;
      case "wander": {
        const r = moveToward(n, n.target, n.speed, dt, W);
        if (r === "arrived") think(n, W); else if (r === "blocked") startStand(n, rand(1, 3)); break; }
      case "gather": {
        const r = moveToward(n, n.slot, n.speed, dt, W);
        if (r === "arrived") startTalk(n, W);
        else if (r === "blocked" && ++n.blocked > 30) { n.pos = n.slot; startTalk(n, W); }   // 길이 막혀 못 가면 자리로 바로 옮긴다
        break; }
      case "talk": {
        turnTo(n, bearing(n, n.group.center, W), dt, 6);
        n.gt -= dt; if (n.gt <= 0) { n.gt = rand(3, 8); const g = GESTURES.filter(k => n.actions[k]); if (g.length) setAnim(n, pick(g), true); }
        break; }
    }
    updatePhone(n.phone, n.mode === "call");
    const l = window.Avatar.local(n.pos[0], n.pos[1]);
    n.obj.position.set(l.x, 0, l.z);
    n.obj.rotation.y = Math.PI - n.heading * Math.PI / 180;
    n.mixer.update(dt);
  }
  for (const g of groups) {   // 모두 모였으면 이야기하다가, 시간이 지나면 같이 옮겨 간다
    if (g.members.every(m => m.mode === "talk")) { g.timer -= dt; if (g.timer <= 0) { g.timer = rand(25, 50); newSite(g, W, g.center); } }
  }
}

function handTip(model, bone) {   // 팔 뼈에 가장 멀리 붙은 꼭짓점들의 평균 = 손 위치(뼈 좌표)
  const sm = []; model.traverse(o => { if (o.isSkinnedMesh) sm.push(o); });
  for (const m of sm) {
    const bi = m.skeleton.bones.indexOf(bone); if (bi < 0) continue;
    const g = m.geometry, pos = g.attributes.position, si = g.attributes.skinIndex, sw = g.attributes.skinWeight;
    const mat = new THREE.Matrix4().multiplyMatrices(m.skeleton.boneInverses[bi], m.bindMatrix), pts = [];
    for (let v = 0; v < pos.count; v++) {
      let w = 0; for (let k = 0; k < 4; k++) if (si.getComponent(v, k) === bi) w += sw.getComponent(v, k);
      if (w > 0.5) pts.push(new THREE.Vector3().fromBufferAttribute(pos, v).applyMatrix4(mat));
    }
    if (!pts.length) continue;
    const mx = Math.max(...pts.map(p => p.length())), far = pts.filter(p => p.length() > mx * 0.8);
    return far.reduce((a, p) => a.add(p), new THREE.Vector3()).divideScalar(far.length);
  }
  return null;
}

function makePhone(model) {   // 양손에 폰을 하나씩 준비하고, 전화 중에는 앞으로 나온 손의 것만 보여 준다
  const hands = [];
  for (const name of ["arm-left", "arm-right"]) {
    const bone = model.getObjectByName(name), tip = bone && handTip(model, bone); if (!tip) continue;
    const g = new THREE.Group();
    g.add(new THREE.Mesh(new THREE.BoxGeometry(0.085, 0.15, 0.014), new THREE.MeshStandardMaterial({ color: 0x15171c, roughness: 0.4 })));
    const scr = new THREE.Mesh(new THREE.PlaneGeometry(0.073, 0.13), new THREE.MeshBasicMaterial({ color: 0x7cc4ff })); scr.position.z = 0.0075; g.add(scr);
    g.visible = false; bone.add(g); hands.push({ bone, tip, g });
  }
  return hands.length ? { hands, model } : null;
}
const _q = new THREE.Quaternion(), _q2 = new THREE.Quaternion(), _v = new THREE.Vector3(), _tilt = new THREE.Quaternion().setFromEuler(new THREE.Euler(-1.9, 0, 0));
function updatePhone(ph, on) {
  if (!ph) return;
  if (!on) { ph.hands.forEach(h => h.g.visible = false); return; }
  ph.model.updateMatrixWorld(true);
  let best = null, bz = -Infinity;
  for (const h of ph.hands) { const z = ph.model.worldToLocal(h.bone.localToWorld(_v.copy(h.tip))).z; if (z > bz) { bz = z; best = h; } }
  for (const h of ph.hands) {
    h.g.visible = h === best; if (h !== best) continue;
    const ws = h.bone.getWorldScale(new THREE.Vector3()).x || 1;
    h.g.scale.setScalar(1 / ws); h.g.position.copy(h.tip);
    h.bone.getWorldQuaternion(_q); ph.model.getWorldQuaternion(_q2);
    h.g.quaternion.copy(_q.invert().multiply(_q2).multiply(_tilt));   // 화면이 위(얼굴 쪽)를 보게 모델 기준으로 고정
  }
}

async function start() {
  const W = window.NpcWorld; if (!W || started) return; started = true;
  const loader = new GLTFLoader(), cache = {};
  const load = url => cache[url] ||= new Promise((res, rej) => loader.load(url, res, undefined, rej));
  const gmap = {};
  for (const spec of SPECS) {
    let gltf; try { gltf = await load(spec.url); } catch (e) { console.error("NPC 모델 실패", spec.url, e); continue; }
    const model = clone(gltf.scene);
    model.scale.setScalar(spec.h / new THREE.Box3().setFromObject(model).getSize(new THREE.Vector3()).y);
    const obj = new THREE.Group(); obj.add(model); window.Avatar.scene.add(obj);
    const mixer = new THREE.AnimationMixer(model), actions = {};
    CLIPS.forEach(k => { const c = THREE.AnimationClip.findByName(gltf.animations, k); if (c) actions[k] = mixer.clipAction(c); });
    const phone = spec.role === "caller" ? makePhone(model) : null;
    const n = { obj, mixer, actions, cur: null, pos: null, heading: rand(0, 360), speed: spec.speed, role: spec.role, mode: "stand", timer: 0, phone };
    mixer.addEventListener("finished", e => { if (n.mode === "talk" && e.action === n.cur) setAnim(n, "idle"); });   // 몸짓이 끝나면 다시 서 있기
    if (spec.role === "talker") (gmap[spec.group] ||= { members: [], center: null, timer: rand(25, 50) }).members.push(n), n.group = gmap[spec.group];
    else n.pos = pickSpot(W);
    if (!n.pos && spec.role !== "talker") { obj.removeFromParent(); continue; }
    npcs.push(n);
    if (spec.role === "talker") continue;
    setAnim(n, "idle"); mixer.update(rand(0, 2));
    if (spec.role === "caller") startCall(n);
    else if (spec.role === "watcher") startWatch(n, W);
    else startStand(n, rand(0, 4));
  }
  for (const g of Object.values(gmap)) {   // 모임 장소를 정하고, 멤버는 근처에서 시작해 걸어와 모인다
    const site = pickSpot(W); if (!site) { g.members.forEach(m => { m.pos = pickSpot(W) || [W.bbox[0], W.bbox[1]]; m.mode = "stand"; m.timer = 5; }); continue; }
    g.members.forEach(m => { m.pos = pickSpot(W, site, 7, 14) || site; });
    if (!newSite(g, W, null)) { g.members.forEach(m => startStand(m)); continue; }
    g.members.forEach(m => { m.pos = pickSpot(W, g.center, 7, 14) || g.center; });   // 확정된 모임 장소 근처에서 출발
    groups.push(g);
  }
}

window.Avatar.addUpdater(dt => {
  if (!started) { if (window.Avatar.local(0, 0)) start(); return; }   // 기준점이 생긴 뒤(걷기 모드 첫 진입)에 소환
  update(dt, window.NpcWorld);
});
