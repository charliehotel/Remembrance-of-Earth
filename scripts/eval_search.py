"""에이전트 검색 단계 평가 (LLM·네트워크 호출 없음, 비용 0).

정답을 아는 업소 기록 하나하나를 '사용자가 기억을 말했다면 이런 단서였을 것'으로 바꿔서
server/agent.py 의 search_tiers(정확/확장 검색)에 넣고, 정답이 후보에 들어오는지·몇 번째인지 잰다.
단서 해석(LLM)은 이 평가에 포함되지 않는다. 해석이 완벽하다고 가정한 상한선이다.

사용: python3 scripts/eval_search.py [--misses N]
"""
import sys, re, statistics, argparse
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "server"))
import agent

ap = argparse.ArgumentParser()
ap.add_argument("--misses", type=int, default=0, help="시나리오별로 놓친 사례를 N건씩 출력")
args = ap.parse_args()

db, parcels = agent.load_db()
ANCHORS = [(j, p) for j, p in parcels.items() if p.get("anchor")]
TOP = 5                                    # 화면에 보이는 후보 수(정확·확장 각각)

def years_of(r):
    s, e = agent._ym(r["start"], 1992), agent._ym(r["end"], 2026.9)
    s, e = int(s), int(min(e, 2025.99))
    return s, max(s, e)

def terms_of(r):
    raw = r["category"] or r.get("category_ai", "")
    return [t for t in re.split(r"[\s/·,()]+", raw) if len(t) >= 2]

def key(r): return (r["jibun"], r["name"])

def clue(r, year, *, name=False, floor=False, anchor="", terms=None):
    return {"year_from": year, "year_to": year, "categories": terms if terms is not None else terms_of(r),
            "name_hints": [r["name"][:2]] if name else [], "floor": (r["floor"] + "층") if floor and r["floor"] else "",
            "anchor": anchor, "radius_m": 0}

def near_anchor(r, lo=0, hi=50):
    """가장 가까운 랜드마크가 lo 초과 hi 이하 거리에 있으면 그 이름. (기본 확장 반경이 50m 이므로 hi 기본값도 50)"""
    if not r["lon"]: return None
    best = min(((agent._dist_m((float(p["lon"]), float(p["lat"])), (r["lon"], r["lat"])), p["anchor"]) for _, p in ANCHORS), default=None)
    return best[1] if best and lo < best[0] <= hi else None

def option_has(opt, r):
    """에이전트가 낸 선택지에 정답 업소가 속하는지(사용자가 사실대로 답한다고 가정)."""
    if opt["kind"] == "floor": return r["floor"] == opt["value"]
    if opt["kind"] == "anchor" and r["lon"]:
        return agent._dist_to(agent.resolve_anchor(opt["anchor"], parcels)[0], (r["lon"], r["lat"])) <= opt["radius_m"]
    return False

Q = {"asked": 0, "answerable": 0, "total": 0}; S7_TARGETS = set()
def asked(r):
    """S1 단서로 검색 → 에이전트가 가르는 질문을 하면, 정답이 속한 선택지로 사용자가 답한 단서를 만든다."""
    if not terms_of(r): return None
    Q["total"] += 1
    c0 = clue(r, mid(r)); ex, _, _ = agent.search_tiers(db, parcels, c0, 0, limit=10 ** 6)
    q = agent.split_question(ex, parcels, c0)
    if not q: return None
    Q["asked"] += 1
    opt = next((o for o in q["options"] if option_has(o, r)), None)
    if not opt: return None
    Q["answerable"] += 1; S7_TARGETS.add(key(r))
    c1 = dict(c0)
    if opt["kind"] == "floor": c1["floor"] = opt["value"] + "층"
    else: c1["anchor"], c1["radius_m"] = opt["anchor"], opt["radius_m"]
    return (c1, 0)

def shifts(r, k, level):
    """기억한 시기가 실제 영업 기간에서 k년 벗어난 경우를 이른 쪽·늦은 쪽 둘 다 만든다."""
    if not terms_of(r): return None
    s0, e0 = years_of(r); cases = []
    if r["end"] and e0 + k <= 2025: cases.append((clue(r, e0 + k), level))
    if s0 - k >= 1992: cases.append((clue(r, s0 - k), level))
    return cases or None

# 시나리오: (이름, 설명, 단서 만들기(r) → (clue, level) 또는 그 목록, 또는 None)
def mid(r): s, e = years_of(r); return (s + e) // 2
SCEN = [
    ("S1 업종+시기",       "정확한 시기와 업종만 기억",                 lambda r: (clue(r, mid(r)), 0) if terms_of(r) else None),
    ("S2 +층",             "S1에 층까지 기억",                          lambda r: (clue(r, mid(r), floor=True), 0) if terms_of(r) and r["floor"] else None),
    ("S3 +상호 앞 두 글자", "S1에 상호 앞 두 글자까지 기억",            lambda r: (clue(r, mid(r), name=True), 0) if terms_of(r) else None),
    ("S4 +랜드마크 근처(50m 이내)", "S1에 '창천감리교회 근처' 같은 위치까지 기억(실제 거리 50m 이내)", lambda r: (clue(r, mid(r), anchor=near_anchor(r)), 0) if terms_of(r) and near_anchor(r) else None),
    ("S4b 랜드마크에서 50~100m", "위치를 '근처'라고만 기억했지만 실제로는 50~100m. '범위 넓히기' 1회 후(반경 100m)", lambda r: (clue(r, mid(r), anchor=near_anchor(r, 50, 100)), 1) if terms_of(r) and near_anchor(r, 50, 100) else None),
    ("S7 가르는 질문에 답함", "S1 단서로 검색 → 에이전트가 되물은 질문(층 또는 위치)에 사용자가 사실대로 한 번 답한 뒤", asked),
    ("S5a 시기 1년 착오(±1)", "기억한 시기가 실제 영업 기간에서 1년 벗어남(이른 쪽·늦은 쪽 둘 다). 기본 범위(±2년)에서 확장 구간으로 나옴", lambda r: shifts(r, 1, 0)),
    ("S5b 시기 2년 착오(±2)", "2년 벗어남. 기본 범위의 한계", lambda r: shifts(r, 2, 0)),
    ("S6a 시기 3년 착오(±3)", "3년 벗어남. 기본 범위로는 불가, '범위 넓히기' 1회 후(±4년)", lambda r: shifts(r, 3, 1)),
    ("S6b 시기 4년 착오(±4)", "4년 벗어남. '범위 넓히기' 1회 후의 한계", lambda r: shifts(r, 4, 1)),
]

def run(r, c, level):
    ex, wi, _ = agent.search_tiers(db, parcels, c, level, limit=10 ** 6)
    ek = [key(x) for x in ex]; wk = [key(x) for x in wi]
    t = key(r)
    if t in ek: return "exact", ek.index(t) + 1, len(ex)
    if t in wk: return "wide", len(ex) + wk.index(t) + 1, len(ex)
    return "miss", None, len(ex)

def group_of(r):
    core = parcels[r["jibun"]]["core"] if r["jibun"] in parcels else False
    return ("연세로12길" if core else "반경150m") + "·" + ("인허가(A)" if r["grade"] == "A" else "로드뷰(C)")

def pct(n, d): return f"{100 * n / d:.0f}%" if d else "-"

targets = [r for r in db if r["start"] and (r["category"] or r.get("category_ai"))]
print(f"정답 후보 업소 {len(targets)}건 · 시나리오 {len(SCEN)}개 · 화면 노출 상위 {TOP}건(정확/확장 각각)\n")

for name, desc, build in SCEN:
    rows, miss = {}, []
    for r in targets:
        b = build(r)
        if not b: continue
        for c, level in ([b] if isinstance(b, tuple) else b):
            tier, rank, nex = run(r, c, level)
            rows.setdefault(group_of(r), []).append((tier, rank, nex))
            rows.setdefault("전체", []).append((tier, rank, nex))
            if tier == "miss" or (rank or 0) > TOP * 2: miss.append((r, tier, rank, nex))
    print(f"### {name} — {desc}")
    print("| 구분 | 건수 | 정확 구간에 포함 | 상위5 안(정확·확장 합산 순서) | 후보에 들어옴(전체) | 놓침 | 순위 중앙값 | 정확 구간 후보 수 중앙값 |")
    print("|---|---|---|---|---|---|---|---|")
    for g in sorted(rows, key=lambda g: (g != "전체", g)):
        v = rows[g]; n = len(v)
        ex_n = sum(1 for t, _, _ in v if t == "exact")
        top5 = sum(1 for t, rk, _ in v if rk and rk <= TOP)
        found = sum(1 for t, _, _ in v if t != "miss")
        rks = [rk for _, rk, _ in v if rk]
        print(f"| {g} | {n} | {pct(ex_n, n)} | {pct(top5, n)} | {pct(found, n)} | {n - found} | {statistics.median(rks) if rks else '-'} | {statistics.median(x for _, _, x in v):.0f} |")
    print()
    if name.startswith("S7"):
        same = [r for r in targets if key(r) in S7_TARGETS]
        rs = [run(r, clue(r, mid(r)), 0) for r in same]
        top5 = sum(1 for tr, rk, _ in rs if rk and rk <= TOP)
        print(f"- 질문이 만들어진 경우 {Q['asked']}건/{Q['total']}건, 그중 정답이 선택지에 속한 경우 {Q['answerable']}건")
        print(f"- 같은 {len(same)}건의 질문 전(S1): 상위5 안 {pct(top5, len(rs))} · 순위 중앙값 {statistics.median(rk for _, rk, _ in rs if rk):.0f} · 정확 구간 후보 수 중앙값 {statistics.median(n for _, _, n in rs):.0f}")
        print()
    for r, tier, rank, nex in miss[:args.misses]:
        print(f"   · 놓침/하위: {r['jibun']} {r['name']} ({r['start'][:7]}~{r['end'][:7]}, {r['category'] or r.get('category_ai')}) → {tier}, 순위 {rank}, 정확 후보 {nex}건")
    if args.misses and miss: print()
