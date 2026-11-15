// 걷기 모드의 행인(사람·동물). 역할마다 행동이 다르다.
//  walker : 도로를 걷다가 서 있거나 건물을 구경한다
//  watcher: 건물을 올려다보며 구경하고, 가끔 다른 곳으로 옮겨 간다
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
  P("walker"), P("walker"),
  P("talker", 0), P("talker", 0), P("talker", 0),   // 이야기 모임 A (3명)
  P("talker", 1), P("talker", 1),                   // 이야기 모임 B (2명)
  animal("dog", 0.6, 1.1), animal("fox", 0.55, 1.0), animal("cat", 0.35, 0.9),
  animal("bunny", 0.4, 0.8), animal("pig", 0.6, 0.7), animal("panda", 0.9, 0.7),
];
const CLIPS = ["idle", "walk", "interact-left", "interact-right", "emote-yes", "emote-no", "eat", "dance"];
// (전화 동작은 핸드폰 모델 없이는 빈손으로 멈춘 것처럼 보여서 뺐다)
   // 전화 자세로 쓸 동작(앞에서부터 있는 것). 화면에서 어색하면 이 순서를 바꾼다
const GESTURES = ["emote-yes", "emote-no", "interact-left", "interact-right"];

const rng = (() => { let a = 20260101; return () => { a = (a + 0x6D2B79F5) | 0; let t = Math.imul(a ^ a >>> 15, 1 | a); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; }; })();
const rand = (a, b) => a + rng() * (b - a);
const pick = arr => arr[Math.floor(rng() * arr.length)];
const npcs = [], groups = []; let started = false, clockT = 0;
// 행인은 내 캐릭터 주변에만 있다: 소환은 NEAR_MIN~NEAR_MAX m 안, LEAVE_R m 넘게 멀어지면 다시 내 주변으로 옮겨 온다(멀리 있는 행인은 어차피 안 보이므로)
const NEAR_MIN = 30, NEAR_MAX = 70, LEAVE_R = 100;

const bearing = (n, p, W) => Math.atan2((p[0] - n.pos[0]) * W.KX, (p[1] - n.pos[1]) * W.KY) * 180 / Math.PI;
const dist = (n, p, W) => Math.hypot((p[0] - n.pos[0]) * W.KX, (p[1] - n.pos[1]) * W.KY);
const turnTo = (n, deg, dt, rate = 8) => { const d = ((deg - n.heading + 540) % 360) - 180; n.heading = (n.heading + d * Math.min(1, dt * rate) + 360) % 360; return Math.abs(d); };

function pickSpot(W, near, dmin = 0, dmax = 0) {   // 걸을 수 있는 빈 점. near가 있으면 그 주변 dmin~dmax m, 없으면 내 캐릭터 주변
  if (!near) { near = W.player(); dmin = 15; dmax = NEAR_MAX; }
  if (!near) return null;
  for (let i = 0; i < 400; i++) {
    const a = rand(0, Math.PI * 2), d = rand(dmin, dmax), p = [near[0] + Math.sin(a) * d / W.KX, near[1] + Math.cos(a) * d / W.KY];
    if (W.free(p[0], p[1])) return p;
  }
  return null;
}
const aroundMe = W => pickSpot(W, W.player(), NEAR_MIN, NEAR_MAX) || pickSpot(W, W.player(), 10, NEAR_MAX + 25);

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

function relocate(n, W) {   // 내 캐릭터에서 너무 멀어진 행인을 주변의 다른 곳으로 옮긴다
  const p = aroundMe(W); if (!p) return;
  n.pos = p; n.heading = rand(0, 360);
  if (n.role === "watcher") startWatch(n, W); else startStand(n, rand(0, 3));
}
function regroup(g, W) {   // 이야기 모임을 통째로 내 주변으로 옮긴다
  for (let i = 0; i < 6; i++) {
    const a = aroundMe(W); if (!a) return;
    if (newSite(g, W, a)) { g.members.forEach(m => { m.pos = pickSpot(W, g.center, 7, 14) || g.center; }); g.timer = rand(25, 50); return; }
  }
}

function update(dt, W) {
  clockT += dt;
  const me = W.player(); if (!me) return;
  for (const n of npcs) {
    if (n.role !== "talker" && dist(n, me, W) > LEAVE_R) relocate(n, W);
    switch (n.mode) {
      case "stand": n.timer -= dt; if (n.timer <= 0) think(n, W); break;
      case "watch": {   // 건물 쪽을 보며 천천히 좌우로 둘러본다
        turnTo(n, bearing(n, n.look, W) + Math.sin(clockT * 0.5 + n.phase) * 28, dt, 3);
        n.timer -= dt; if (n.timer <= 0) think(n, W); break; }
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
    const l = window.Avatar.local(n.pos[0], n.pos[1]);
    n.obj.position.set(l.x, 0, l.z);
    n.obj.rotation.y = Math.PI - n.heading * Math.PI / 180;
    n.mixer.update(dt);
  }
  for (const g of groups) {   // 모두 모였으면 이야기하다가, 시간이 지나면 같이 옮겨 간다
    if (g.center && dist({ pos: g.center }, me, W) > LEAVE_R) { regroup(g, W); continue; }
    if (g.members.every(m => m.mode === "talk")) { g.timer -= dt; if (g.timer <= 0) { g.timer = rand(25, 50); newSite(g, W, g.center); } }
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
    const n = { obj, mixer, actions, cur: null, pos: null, heading: rand(0, 360), speed: spec.speed, role: spec.role, mode: "stand", timer: 0 };
    mixer.addEventListener("finished", e => { if (n.mode === "talk" && e.action === n.cur) setAnim(n, "idle"); });   // 몸짓이 끝나면 다시 서 있기
    if (spec.role === "talker") (gmap[spec.group] ||= { members: [], center: null, timer: rand(25, 50) }).members.push(n), n.group = gmap[spec.group];
    else n.pos = pickSpot(W);
    if (!n.pos && spec.role !== "talker") { obj.removeFromParent(); continue; }
    npcs.push(n);
    if (spec.role === "talker") continue;
    setAnim(n, "idle"); mixer.update(rand(0, 2));
    if (spec.role === "watcher") startWatch(n, W);
    else startStand(n, rand(0, 4));
  }
  for (const g of Object.values(gmap)) {   // 모임 장소를 정하고, 멤버는 근처에서 시작해 걸어와 모인다
    const site = pickSpot(W); if (!site) { g.members.forEach(m => { m.pos = pickSpot(W) || W.player(); m.mode = "stand"; m.timer = 5; }); continue; }
    g.members.forEach(m => { m.pos = pickSpot(W, site, 7, 14) || site; });
    if (!newSite(g, W, null)) { g.members.forEach(m => startStand(m)); continue; }
    g.members.forEach(m => { m.pos = pickSpot(W, g.center, 7, 14) || g.center; });   // 확정된 모임 장소 근처에서 출발
    groups.push(g);
  }
}

window.Avatar.addUpdater(dt => {
  if (!started) { if (window.Avatar.local(0, 0) && window.NpcWorld?.player()) start(); return; }   // 기준점이 생기고 내 캐릭터가 놓인 뒤(걷기 모드 첫 진입)에 내 주변으로 소환
  update(dt, window.NpcWorld);
});
