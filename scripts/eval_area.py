"""골목의 연대기(영역 분석) 평가.

A. 오프라인 검증(AI·네트워크 없음, 비용 0)
   1. 불변식: 임의 영역 N개에서 리포트의 합계·순서·범위가 모순되지 않는지
   2. 결정성: 같은 영역을 두 번 돌리면 리포트가 완전히 같은지
   3. 구간 보정 효과: 관측이 있는 업소에서 '기록만'의 구간 폭 대비 보정 후 폭, 기록상 폐업일이 얼마나 늦은지
B. AI 해설 평가(--ai, 공급자는 .env 의 LLM_PROVIDER 를 따른다. 개발 중에는 cliproxyapi)
   질문 40개 × 영역 몇 개에서 관점(focus) 분류 정확도, 숫자 충실도(모델이 지어낸 숫자가 든 문장 비율),
   답을 피하는 비율, 범위 밖 질문을 정확히 거절하는 비율, 웹 검색 사용의 적절성, 한계 언급 비율을 잰다.

실수로 Liner 크레딧을 쓰지 않도록 Liner 일 때는 --liner 와 --max-cost 를 함께 줘야 AI 평가가 실행된다.
사용: python3 scripts/eval_area.py [--areas 12] [--ai] [--ai-areas 2] [--workers 3] [--out 경로.jsonl]
"""
import sys, json, re, random, statistics, argparse, threading, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "server"))
import agent, analysis as A, area_agent, liner

ap = argparse.ArgumentParser()
ap.add_argument("--areas", type=int, default=12, help="오프라인 불변식 검사용 임의 영역 수(×10 배수로 돌린다)")
ap.add_argument("--ai", action="store_true", help="AI 해설 평가도 실행")
ap.add_argument("--ai-areas", type=int, default=2, help="질문마다 시험할 영역 수(1~3)")
ap.add_argument("--workers", type=int, default=3)
ap.add_argument("--set", default="dev", choices=["dev", "heldout", "both"], help="질문 집합: dev(프롬프트 개선에 쓴 40개) / heldout(개선에 쓰지 않은 30개) / both")
ap.add_argument("--seed", type=int, default=1)
ap.add_argument("--out", default="eval_area.jsonl")
ap.add_argument("--from-log", default="", help="실행 없이 저장된 로그만 다시 집계")
ap.add_argument("--liner", action="store_true")
ap.add_argument("--max-cost", type=float, default=0.0)
ap.add_argument("--max-errors", type=int, default=5)
args = ap.parse_args()

rows, parcels = agent.load_db()
rng = random.Random(args.seed)
pct = lambda n, d: f"{100 * n / d:.0f}%" if d else "-"

# ---------- 영역 만들기: 임의 필지 + 반경 ----------
NONSITE = {"도", "철", "구", "천", "제", "하", "유", "수"}
site = [j for j, p in parcels.items() if p.get("jimok") not in NONSITE and any(r["jibun"] == j for r in rows)]
ctr = {j: (float(parcels[j]["lon"]), float(parcels[j]["lat"])) for j in site}
def area_around(j, r): return [k for k in site if agent._dist_m(ctr[j], ctr[k]) <= r]

# =============== A. 오프라인 ===============
def invariants(js):
    bad = []
    rep = A.report(rows, parcels, js)
    o = rep["overview"]; n = sum(1 for r in rows if r["jibun"] in set(js))
    if o["n_shops"] != n: bad.append(f"업소 수 {o['n_shops']}≠{n}")
    if n and sum(o["evidence"].values()) != n: bad.append("근거 등급 합 불일치")
    if n and sum(o["state"].values()) != n: bad.append("상태 합 불일치")
    C = rep["composition"]
    for y in (C["years"] if C else []):
        by = C["by_year"][str(y)]
        for g, (c, p) in by.items():
            if c > p: bad.append(f"{y} {g} 확실>가능")
        if C["total"][str(y)] != [sum(v[0] for v in by.values()), sum(v[1] for v in by.values())]: bad.append(f"{y} 합계 불일치")
    for ch in (C or {}).get("change", []):
        for x in ch["items"]:
            if x["delta"][0] > x["delta"][1]: bad.append("증감 범위 순서")
            if (x["dir"] == "증가") != (x["delta"][0] > 0) or (x["dir"] == "감소") != (x["delta"][1] < 0): bad.append("증감 방향 분류")
    V = rep["survival"]
    for g in ([V["all"]] if "all" in V else []) + V.get("groups", []):
        for t, (lo, hi) in g["at"].items():
            if not (0 <= lo <= hi <= 1): bad.append(f"생존율 범위 {t}")
        for a, b in (("3", "5"), ("5", "10")):
            if g["at"][b][0] > g["at"][a][0] + 1e-9 or g["at"][b][1] > g["at"][a][1] + 1e-9: bad.append("생존율이 시간에 따라 증가")
        if g["n"] < A.MIN_N: bad.append("표본 부족인데 수치 공개")
    H = rep["history"]
    if H and H["overlap_share"] is not None and not (0 <= H["overlap_share"] <= 1): bad.append("겹침 비율 범위")
    for x in A.prepare([r for r in rows if r["jibun"] in set(js)], rep["limits"]["delay_years"]):
        if x["e_lo"] > x["e_hi"] + 1e-9 or x["s_lo"] > x["s"] + 1e-9: bad.append(f"구간 순서 {x['name']}"); break
    if not A.facts(rep) and n: bad.append("사실 목록 비어 있음")
    return bad, rep

print("## A. 오프라인 검증\n")
N = args.areas * 10
fails, tested = [], 0
for i in range(N):
    j = rng.choice(site); js = area_around(j, rng.choice([30, 50, 80, 120, 200, 400]))
    if not js: continue
    bad, rep = invariants(js); tested += 1
    if bad: fails.append((j, len(js), bad[:3]))
    if i % 10 == 0:
        again = A.report(rows, parcels, js)
        if json.dumps(again, sort_keys=True) != json.dumps(rep, sort_keys=True): fails.append((j, len(js), ["비결정적 리포트"]))
print(f"- 임의 영역 {tested}개(반경 30~400m)에서 불변식 위반 {len(fails)}건" + ("" if not fails else ": " + "; ".join(f"{j}({n}필지) {b}" for j, n, b in fails[:5])))
print(f"- 결정성: 영역 {tested // 10 + 1}개를 두 번 돌려 리포트가 달라진 경우 {sum(1 for f in fails if '비결정적 리포트' in f[2])}건")

delay, ds = A.delay_assumption(rows)
items = A.prepare(rows, delay)
closed = [x for x in items if x["state"] == "closed"]
ev = {k: sum(1 for x in closed if x["ev"] == k) for k in (A.EV_OBS, A.EV_PART, A.EV_REC)}
print(f"\n### 구간 보정 효과(폐업 {len(closed)}건)")
print(f"- 근거 등급: 관측 확인 {ev[A.EV_OBS]}건({pct(ev[A.EV_OBS], len(closed))}) · 부분 관측 {ev[A.EV_PART]}건({pct(ev[A.EV_PART], len(closed))}) · 기록만 {ev[A.EV_REC]}건({pct(ev[A.EV_REC], len(closed))})")
w = [x["e_hi"] - x["e_lo"] for x in closed if x["ev"] != A.EV_REC]
if w: print(f"- 관측이 있는 {len(w)}건의 종료 시점 구간 폭: 중앙값 {statistics.median(w):.1f}년, 2년 이하 {pct(sum(1 for v in w if v <= 2), len(w))}, 4년 초과 {pct(sum(1 for v in w if v > 4), len(w))}")
if ds:
    print(f"- 기록상 폐업일이 마지막 영업 관측보다 늦은 정도(조사 간격 포함 상한, {len(ds)}건): 중앙값 {statistics.median(ds):.1f}년, 75백분위 {A._pct(ds, 0.75):.1f}년, 1년 이상 {pct(sum(1 for v in ds if v >= 1), len(ds))}, 3년 이상 {pct(sum(1 for v in ds if v >= 3), len(ds))}, 최대 {max(ds):.1f}년")
    print(f"- 관측 없는 업소({ev[A.EV_REC]}건)에는 이 75백분위({delay:.1f}년)를 가정해 구간 폭 {delay:.1f}년을 둔다. 기록만 쓰면 폭 0(한 점)이라 불확실성이 숨는다.")
sa = sum(1 for r in rows if "seen_after_close" in r.get("flags", ""))
print(f"- 기록상 폐업 이후에도 간판이 보인 업소 {sa}건(가정 '신고는 폐업 뒤'의 예외, 상한이 아니라 점으로 처리)")

if not args.ai and not args.from_log:
    print("\n(AI 해설 평가는 --ai 로 실행)"); sys.exit(0)

# =============== B. AI 해설 ===============
prov = liner.provider()
if not args.from_log and prov != "cliproxyapi" and not (args.liner and args.max_cost > 0):
    sys.exit(f"\n현재 공급자가 '{prov}'(Liner)입니다. 크레딧 보호를 위해 AI 평가를 중단합니다.\n  · 테스트: .env 에 LLM_PROVIDER=cliproxyapi\n  · 최종 평가: --ai --liner --max-cost 0.1 처럼 상한을 함께 지정")

# (질문, 기대 관점, 분류) 분류: ans=자료로 답할 수 있음 · out=범위 밖(거절이 정답) · why=원인 질문(웹 검색 기대)
Q = [
    ("이 영역 업종 구성이 어떻게 바뀌었어?", "composition", "ans"), ("최근 10년간 업종 변화가 가장 큰 건 뭐야?", "composition", "ans"),
    ("카페가 늘었어?", "composition", "ans"), ("술집은 줄었어?", "composition", "ans"), ("2010년에는 어떤 업종이 많았어?", "composition", "ans"),
    ("요즘은 어떤 업종이 제일 많아?", "composition", "ans"), ("20년 전이랑 비교하면 뭐가 달라졌어?", "composition", "ans"), ("한식집은 예전보다 많아졌어 적어졌어?", "composition", "ans"),
    ("카페는 얼마나 버텼어?", "survival", "ans"), ("술집은 보통 몇 년 영업해?", "survival", "ans"), ("5년 넘게 버티는 가게는 얼마나 돼?", "survival", "ans"),
    ("어떤 업종이 제일 오래 영업했어?", "survival", "ans"), ("한식집 생존율 알려줘", "survival", "ans"), ("음식점은 보통 얼마나 하다가 닫아?", "survival", "ans"), ("가게들이 대체로 얼마나 오래 가?", "survival", "ans"),
    ("가게가 자주 바뀌는 자리야?", "history", "ans"), ("가게가 문 닫고 다음 가게가 들어오기까지 얼마나 걸려?", "history", "ans"), ("가게 교체 주기가 어떻게 돼?", "history", "ans"),
    ("공실 기간은 보통 얼마야?", "history", "ans"), ("한 자리에 가게가 몇 번이나 바뀌었어?", "history", "ans"),
    ("이 영역 한마디로 요약해줘", "overview", "ans"), ("업소가 몇 곳이야?", "overview", "ans"), ("데이터는 얼마나 믿을 만해?", "overview", "ans"), ("지금 영업 중인 가게는 몇 곳이야?", "overview", "ans"),
    ("폐업한 가게는 몇 곳이야?", "overview", "ans"), ("근거 등급이 어떻게 돼?", "overview", "ans"),
    ("여기에 카페를 차리면 잘될까?", "none", "out"), ("내년에는 어떤 업종이 뜰까?", "none", "out"), ("월 매출이 얼마나 나와?", "none", "out"), ("임대료는 얼마야?", "none", "out"),
    ("유동인구는 얼마나 돼?", "none", "out"), ("창업하기 좋은 업종 추천해줘", "none", "out"), ("오늘 날씨 어때?", "none", "out"), ("이 가게들 맛집이야?", "none", "out"),
    ("왜 술집이 줄었어?", "composition", "why"), ("카페가 늘어난 이유가 뭐야?", "composition", "why"), ("왜 가게들이 오래 못 버텨?", "survival", "why"),
    ("이 골목이 변한 배경이 뭐야?", "composition", "why"), ("분식집이 줄어든 원인이 뭐야?", "composition", "why"), ("업종이 바뀐 이유가 뭘까?", "composition", "why"),
]
assert len(Q) == 40
Q_HELD = [
    ("이 동네 가게 종류가 예전이랑 많이 달라졌나?", "composition", "ans"), ("옛날엔 뭐 파는 집이 제일 많았어?", "composition", "ans"), ("미용실 같은 서비스업은 늘고 있어?", "composition", "ans"),
    ("게임·오락 쪽은 어떻게 됐어?", "composition", "ans"), ("최근에 새로 많이 생기는 업종이 있어?", "composition", "ans"), ("지금이랑 2005년의 업종 분포를 비교해줘", "composition", "ans"),
    ("치킨집이나 호프집은 몇 년이나 가?", "survival", "ans"), ("가게 열면 3년 안에 망하는 비율은?", "survival", "ans"), ("10년 넘게 한 가게는 많아?", "survival", "ans"),
    ("평균적으로 몇 년 장사하고 문 닫아?", "survival", "ans"), ("중식당 영업 기간이 어때?", "survival", "ans"), ("어느 업종이 제일 빨리 망해?", "survival", "ans"),
    ("한 건물에 가게가 계속 바뀌는 편이야?", "history", "ans"), ("가게가 나가면 바로 다른 가게가 들어와?", "history", "ans"), ("빈 가게로 비어 있는 기간이 길어?", "history", "ans"), ("자리 회전율이 높은 편이야?", "history", "ans"),
    ("이 영역에 대해 알려줘", "overview", "ans"), ("분석에 쓴 자료가 몇 건이야?", "overview", "ans"), ("자료 신뢰도가 어때?", "overview", "ans"), ("관측으로 확인된 가게가 얼마나 돼?", "overview", "ans"),
    ("여기서 장사하면 돈 벌 수 있어?", "none", "out"), ("앞으로 가게가 더 줄어들까?", "none", "out"), ("가장 인기 있는 가게가 어디야?", "none", "out"), ("건물주가 누구야?", "none", "out"),
    ("점심 메뉴 추천해줘", "none", "out"), ("권리금은 얼마쯤이야?", "none", "out"),
    ("카페가 많아진 건 무슨 이유야?", "composition", "why"), ("왜 오래된 가게들이 사라졌을까?", "survival", "why"), ("코로나가 영향이 있었어?", "composition", "why"), ("상권이 쇠퇴한 원인이 뭐야?", "composition", "why"),
]
assert len(Q_HELD) == 30
if args.set == "heldout": Q = Q_HELD
elif args.set == "both": Q = Q + Q_HELD
REFUSE = re.compile(r"(답변|답|안내|제공|확인|단정|말씀)(해 ?드릴|드릴|할)? ?수 없|알 수 없|데이터(에는|에)? ?(포함되어 )?(있지 않|없)|보유하고 있지 않|제공되지 않|포함되어 있지 않|정보가 없")
LIMIT = re.compile(r"기록 기준|범위|관측|표본|한계|불확실|추정|가정")

# 질문을 시험할 영역: 연세로12길 핵심 25필지 / 창천감리교회 100m / 교회에서 먼 반경 150m 쪽 한 곳
core_js = [j for j in site if parcels[j].get("core")]
church = next(j for j in site if parcels[j].get("anchor") == "창천감리교회")
AREAS = [("핵심 25필지", core_js), ("교회 100m", area_around(church, 100)), ("전체 250필지", list(site))]
reports = [(n, js, A.report(rows, parcels, js)) for n, js in AREAS[:max(1, min(3, args.ai_areas))]]

lock = threading.Lock(); st = {"cost": 0.0, "errors": 0, "stop": None}
outf = open(args.out, "w", encoding="utf-8") if not args.from_log else None
done = []
def run_one(task):
    if st["stop"]: return None
    (q, exp, kind), (aname, js, rep) = task; t0 = time.time(); rec = {"q": q, "exp": exp, "kind": kind, "area": aname, "n_shops": rep["overview"]["n_shops"]}
    try:
        r = area_agent.ask(rep, q)
        sents = [s for s in re.split(r"(?<=[.!?。])\s+", r["answer"]) if s.strip()]
        rec.update(focus=r["focus"], web=r["web"]["used"], web_found=r["web"].get("found", 0), web_n=r["web"].get("n", 0), dropped=r["dropped"], sentences=r["sentences"], answer=r["answer"], raw=r.get("raw", ""),
                   refuse_first=bool(sents and REFUSE.search(sents[0])), refuse_any=bool(REFUSE.search(r["answer"])), has_num=bool(re.search(r"\d", r["answer"])),
                   mentions_limit=bool(LIMIT.search(r["answer"])), limit_added=r.get("limit_added", False), cost=r["cost_usd"], model=r["model"])
    except Exception as e:
        rec["error"] = f"{type(e).__name__}: {str(e)[:160]}"
    rec["sec"] = round(time.time() - t0, 1)
    with lock:
        st["errors"] = st["errors"] + 1 if rec.get("error") else 0
        st["cost"] += rec.get("cost") or 0
        if st["errors"] >= args.max_errors: st["stop"] = "연속 오류"
        if prov != "cliproxyapi" and st["cost"] > args.max_cost: st["stop"] = "비용 상한 초과"
        outf.write(json.dumps(rec, ensure_ascii=False) + "\n"); outf.flush(); done.append(rec)
        print(f"  [{len(done)}] {q[:22]:<22} {aname} → " + (rec.get("error") or f"{rec['focus']}{' 웹' if rec['web'] else ''}{' 거절' if rec['refuse_first'] else ''}{' 숫자제외' + str(rec['dropped']) if rec['dropped'] else ''}"), flush=True)
    return rec

if args.from_log:
    done = [json.loads(l) for l in open(args.from_log, encoding="utf-8")]
else:
    tasks = [(q, r) for q in Q for r in [(a, js, rp) for a, js, rp in reports]]
    print(f"\n## B. AI 해설 평가 — 공급자 {prov} · 질문 {len(Q)}개 × 영역 {len(reports)}개 = {len(tasks)}회\n", flush=True)
    t_start = time.time()
    with ThreadPoolExecutor(args.workers) as ex: list(ex.map(run_one, tasks))
    outf.close()
    print(f"\n소요 {time.time() - t_start:.0f}초" + (f" · 중단: {st['stop']}" if st["stop"] else "") + (f" · 누적 비용 ${st['cost']:.4f}" if prov != "cliproxyapi" else ""), flush=True)

ok = [r for r in done if not r.get("error")]
print(f"\n응답 {len(ok)}건 / 오류 {len(done) - len(ok)}건\n")
print("| 구분 | 건수 | 관점 분류 정확도 | 숫자가 든 문장 중 제외된 비율 | 숫자 제외가 있던 답 | 첫 문장에서 답 회피 | 거절 문구 포함 | 답에 숫자 포함 | 한계 언급 | 웹 검색 사용 |")
print("|---|---|---|---|---|---|---|---|---|---|")
for name, f in (("전체", lambda r: True), ("자료로 답할 수 있는 질문", lambda r: r["kind"] == "ans"), ("범위 밖 질문(거절이 정답)", lambda r: r["kind"] == "out"), ("원인 질문(웹 검색 기대)", lambda r: r["kind"] == "why")):
    g = [r for r in ok if f(r)]
    if not g: continue
    sent = sum(r["sentences"] for r in g)
    print(f"| {name} | {len(g)} | {pct(sum(1 for r in g if r['focus'] == r['exp']), len(g))} | {pct(sum(r['dropped'] for r in g), sent)} ({sum(r['dropped'] for r in g)}/{sent}) | {pct(sum(1 for r in g if r['dropped']), len(g))} | {pct(sum(1 for r in g if r['refuse_first']), len(g))} | {pct(sum(1 for r in g if r['refuse_any']), len(g))} | {pct(sum(1 for r in g if r['has_num']), len(g))} | {pct(sum(1 for r in g if r['mentions_limit']), len(g))} | {pct(sum(1 for r in g if r['web']), len(g))} |")
wh = [r for r in ok if r["kind"] == "why"]
if wh:
    none_rel = [r for r in wh if r["web_n"] == 0]
    cause_claim = [r for r in none_rel if re.search(r"보도가 있|때문|영향으로|원인은", r["answer"]) and not re.search(r"확인되지|알 수 없|찾지 못", r["answer"])]
    print(f"\n원인 질문 {len(wh)}건: 검색 결과 중 신촌 관련으로 쓴 비율 {pct(sum(r['web_n'] for r in wh), sum(r['web_found'] for r in wh))}({sum(r['web_n'] for r in wh)}/{sum(r['web_found'] for r in wh)}건), 관련 근거가 0건이었던 질문 {len(none_rel)}건 중 원인을 단정한 답 {len(cause_claim)}건")
la = sum(1 for r in ok if r.get("limit_added"))
print(f"\n모델이 한계 언급을 빠뜨려 코드가 덧붙인 답: {la}건/{len(ok)}건")
print("\n관점별 정확도(기대 → 맞힌 비율):")
for fcs in ("composition", "survival", "history", "overview", "none"):
    g = [r for r in ok if r["exp"] == fcs]
    if g: print(f"  - {fcs}: {pct(sum(1 for r in g if r['focus'] == fcs), len(g))} ({len(g)}건)  오분류 → {dict(__import__('collections').Counter(r['focus'] for r in g if r['focus'] != fcs))}")
print("\n문제 사례:")
n = 0
for r in ok:
    why = []
    if r["focus"] != r["exp"]: why.append(f"관점 {r['focus']}≠{r['exp']}")
    if r["kind"] == "ans" and r["refuse_first"]: why.append("답을 피함")
    if r["kind"] == "out" and not r["refuse_any"]: why.append("범위 밖인데 거절 안 함")
    if r["kind"] == "why" and not r["web"]: why.append("원인 질문인데 웹 검색 안 함")
    if r["kind"] != "why" and r["web"]: why.append("웹 검색을 쓰지 않아야 함")
    if r["kind"] == "ans" and not r["has_num"]: why.append("수치 없음")
    if r["dropped"]: why.append(f"숫자 제외 {r['dropped']}/{r['sentences']}문장")
    if why and n < 25:
        n += 1; print(f"  - [{r['area']}] {r['q']} → {', '.join(why)}\n      {r['answer'][:150]}")
errs = [(r["q"], r["error"]) for r in done if r.get("error")]
for q, e in errs[:5]: print(f"  오류: {q} → {e}")
