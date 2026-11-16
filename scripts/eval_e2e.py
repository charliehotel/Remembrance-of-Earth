"""에이전트 종단 평가: 실제 agent.run()(단서 해석 → 검색 → 웹 → 판정)을 대화로 돌려 정답에 도달하는지 잰다.

정답을 아는 업소 기록에서 '사용자가 기억을 말하는 대화'를 만들어 에이전트에 보낸다.
  1턴: 시기와 업종만("2012년 무렵 한식 가게")  →  정답이 1순위가 아니면
  2턴: 층이 기록에 있으면 층, 없으면 상호 첫 글자  →  3턴: 상호 앞 두 글자
상호는 마지막 단서로만 쓰고, 정답을 말해 주지는 않는다.

모델 호출 공급자는 .env 의 LLM_PROVIDER 를 따른다. 개발 중에는 cliproxyapi 로 돌리고(비용 0),
실수로 Liner 크레딧을 쓰지 않도록 Liner 일 때는 --liner 와 --max-cost 를 함께 줘야 실행된다.

사용: python3 scripts/eval_e2e.py [--per-group 8] [--turns 3] [--workers 3] [--out 경로.jsonl]
"""
import sys, json, time, random, argparse, threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "server"))
import agent, liner

ap = argparse.ArgumentParser()
ap.add_argument("--per-group", type=int, default=8, help="그룹(연세로12길 인허가·로드뷰·반경150m 인허가)별 정답 업소 수")
ap.add_argument("--turns", type=int, default=3)
ap.add_argument("--workers", type=int, default=3)
ap.add_argument("--seed", type=int, default=1)
ap.add_argument("--out", default="eval_e2e.jsonl")
ap.add_argument("--liner", action="store_true", help="Liner 로 실행(크레딧 사용). --max-cost 필수")
ap.add_argument("--max-cost", type=float, default=0.0, help="Liner 실행 시 누적 비용 상한(USD)")
ap.add_argument("--from-log", default="", help="실행 없이 저장된 로그(jsonl)만 다시 집계")
ap.add_argument("--max-errors", type=int, default=5, help="연속 오류가 이 수를 넘으면 중단")
args = ap.parse_args()

prov = liner.provider()
if not args.from_log and prov != "cliproxyapi" and not (args.liner and args.max_cost > 0):
    sys.exit(f"현재 공급자가 '{prov}'(Liner)입니다. 크레딧 보호를 위해 중단합니다.\n"
             "  · 테스트: .env 에 LLM_PROVIDER=cliproxyapi\n  · 최종 평가: --liner --max-cost 0.1 처럼 상한을 함께 지정")

db, parcels = agent.load_db()
rng = random.Random(args.seed)

def years_of(r):
    s, e = agent._ym(r["start"], 1992), agent._ym(r["end"], 2026.9)
    s, e = int(s), int(min(e, 2025.99))
    return s, max(s, e)

def group_of(r):
    core = parcels[r["jibun"]]["core"] if r["jibun"] in parcels else False
    return ("연세로12길" if core else "반경150m") + "·" + ("인허가(A)" if r["grade"] == "A" else "로드뷰(C)")

def key(r): return (r["jibun"], r["name"])

pool = {}
for r in db:
    cat = r["category"] or r.get("category_ai")
    if r["start"] and cat and len(r["name"]) >= 2: pool.setdefault(group_of(r), []).append(r)
targets = []
for g in sorted(pool):
    targets += rng.sample(pool[g], min(args.per_group, len(pool[g])))

def messages(r):
    s, e = years_of(r); year = (s + e) // 2
    cat = r["category"] or r.get("category_ai")
    m = [f"{year}년 무렵 {cat} 가게를 찾고 있어"]
    if r["floor"]: m.append(f"{r['floor']}층에 있었어")
    else: m.append(f"상호가 '{r['name'][:1]}'로 시작했던 것 같아")
    m.append(f"상호는 '{r['name'][:2]}'로 시작했어")
    return m[:args.turns]

lock = threading.Lock()
state_ = {"cost": 0.0, "errors": 0, "stop": None}
outf = open(args.out, "w", encoding="utf-8")

def run_case(r):
    state, turns = {}, []
    for i, msg in enumerate(messages(r)):
        if state_["stop"]: break
        t0 = time.time(); cands, done, err = [], None, None
        try:
            for ev in agent.run(msg, state):
                if ev["step"] == "cands": cands = ev["cands"]
                elif ev["step"] == "done": done = ev
        except Exception as e:
            err = f"{type(e).__name__}: {str(e)[:200]}"
        with lock:
            state_["errors"] = state_["errors"] + 1 if err else 0
            if done: state_["cost"] += done.get("cost_usd") or 0
            if state_["errors"] >= args.max_errors: state_["stop"] = "연속 오류"
            if prov != "cliproxyapi" and state_["cost"] > args.max_cost: state_["stop"] = "비용 상한 초과"
        if err or not done:
            turns.append({"turn": i + 1, "msg": msg, "error": err or "응답 없음", "sec": round(time.time() - t0, 1)}); break
        state = done["state"]
        tgt = next((c for c in cands if (c["jibun"], c["name"]) == key(r)), None)
        jd = {j["id"]: j for j in done["result"]["judgements"]}
        last = state.get("last_top") or {}
        turns.append({"turn": i + 1, "msg": msg, "top1": last.get("name"), "hit": (last.get("jibun"), last.get("name")) == key(r),
                      "in_cands": tgt is not None, "target_verdict": jd.get(tgt["id"], {}).get("verdict") if tgt else None,
                      "top1_verdict": jd.get(next((c["id"] for c in cands if (c["jibun"], c["name"]) == (last.get("jibun"), last.get("name"))), ""), {}).get("verdict"),
                      "web": done["web"]["used"], "n_cands": len(cands), "sec": round(time.time() - t0, 1), "model": done["model"]})
        if turns[-1]["hit"]: break
    rec = {"target": {"jibun": r["jibun"], "name": r["name"], "group": group_of(r), "category": r["category"] or r.get("category_ai"),
                      "period": f"{r['start'][:7]}~{r['end'][:7]}", "floor": r["floor"]}, "turns": turns}
    with lock:
        outf.write(json.dumps(rec, ensure_ascii=False) + "\n"); outf.flush()
        print(f"  [{len(done_cases)+1}/{len(targets)}] {r['name']} ({group_of(r)}) → " +
              " / ".join(("✓" if t.get("hit") else ("오류" if t.get("error") else "✗")) for t in turns), flush=True)
        done_cases.append(rec)
    return rec

done_cases = []
if args.from_log:
    done_cases = [json.loads(l) for l in open(args.from_log, encoding="utf-8")]
    targets = []
print(f"공급자 {prov} · 정답 {len(targets)}건 · 최대 {args.turns}턴 · 동시 {args.workers}", flush=True)
t_start = time.time()
with ThreadPoolExecutor(args.workers) as ex: list(ex.map(run_case, targets))
outf.close()
if args.from_log: Path(args.out).unlink(missing_ok=True)

# ---------- 요약 ----------
def pct(n, d): return f"{100 * n / d:.0f}%" if d else "-"
print(f"\n소요 {time.time() - t_start:.0f}초" + (f" · 중단: {state_['stop']}" if state_["stop"] else "") + (f" · 누적 비용 ${state_['cost']:.4f}" if prov != "cliproxyapi" else ""))
print("| 구분 | 건수 | 1턴 1순위 | 1턴 후보에 포함 | 2턴 안 1순위 | 3턴 안 1순위 | 최종 못 맞힘 | 오답을 '확인'(건/턴) | '확인'의 정답률 | 정답 1순위 중 '확인' | 웹 사용(턴) | 턴당 소요(초) |")
print("|---|---|---|---|---|---|---|---|---|---|---|---|")
groups = ["전체"] + sorted({c["target"]["group"] for c in done_cases})
for g in groups:
    cs = [c for c in done_cases if g == "전체" or c["target"]["group"] == g]
    ok = [c for c in cs if c["turns"] and not c["turns"][0].get("error")]
    n = len(ok)
    if not n: continue
    hit_by = lambda k: sum(1 for c in ok if any(t.get("hit") for t in c["turns"][:k]))
    allt = [t for c in ok for t in c["turns"] if not t.get("error")]
    fc = sum(1 for t in allt if not t["hit"] and t.get("top1_verdict") == "확인")
    conf = [t for t in allt if t.get("top1_verdict") == "확인"]; hits = [t for t in allt if t["hit"]]
    print(f"| {g} | {n} | {pct(hit_by(1), n)} | {pct(sum(1 for c in ok if c['turns'][0].get('in_cands')), n)} | {pct(hit_by(2), n)} | {pct(hit_by(3), n)} | {n - hit_by(3)} | {fc}건/{len(allt)}턴 | {pct(sum(1 for t in conf if t['hit']), len(conf))}({len(conf)}) | {pct(sum(1 for t in hits if t.get('top1_verdict') == '확인'), len(hits))}({len(hits)}) | {pct(sum(1 for t in allt if t['web']), len(allt))} | {sum(t['sec'] for t in allt) / len(allt):.0f} |")
errs = [(c["target"]["name"], t["error"]) for c in done_cases for t in c["turns"] if t.get("error")]
if errs:
    print(f"\n오류 {len(errs)}건:")
    for nme, e in errs[:5]: print(f"  - {nme}: {e}")
print("\n끝까지 못 맞힌 사례:")
for c in done_cases:
    if c["turns"] and not any(t.get("hit") for t in c["turns"]) and not c["turns"][-1].get("error"):
        t = c["turns"][-1]; print(f"  - {c['target']['name']} ({c['target']['period']}, {c['target']['category']}) → 마지막 1순위 {t.get('top1')} · 후보 포함 {t.get('in_cands')}")
