"""골목의 연대기: 영역(필지 집합) 분석 리포트. 계산은 전부 코드가 하고 LLM·네트워크 호출은 없다.

핵심 원칙
  · 인허가 기록의 폐업일은 '행정 기록일'이다(폐업신고에 기한이 없다). 그래서 영업 종료를 한 점이 아니라
    구간 [하한, 상한]으로 다룬다. 상한 = 기록상 폐업일(또는 '간판 없음'이 확인된 첫 시점 중 빠른 쪽),
    하한 = 영업 중이 확인된 마지막 시점(간판 마지막 관측). 관측이 없는 업소의 하한은 가정(아래 DELAY)으로 둔다.
  · 근거 등급: 관측 확인(구간 폭 ≤ 2년) / 부분 관측(관측은 있으나 폭이 넓음) / 기록만(관측 없음).
  · 표본이 MIN_N 곳 미만이면 수치를 내지 않고 '표본 부족'으로 표시한다.
  · 모든 수치는 '기록 기준'이다.

report(rows, parcels, jibuns) 가 고정 구조의 리포트(dict)를 돌려준다. 섹션: overview, composition, survival, history, limits.
"""
import re, statistics
import region
from datetime import date

T_NOW = 2026.9                  # 데이터 기준 시점(마지막 로드뷰 조사 2026-06 이후)
MIN_N = 10                      # 이 수 미만이면 수치를 내지 않는다
WIDTH_OK = 2.0                  # 구간 폭이 이 값(년) 이하이면 '관측 확인'
CORE_YEARS = list(range(1995, 2026, 5))
SURVIVAL_T = (3, 5, 10)
EV_OBS, EV_PART, EV_REC = "관측 확인", "부분 관측", "기록만"

# 업종 묶음: (묶음 이름, 키워드). category_ai(상호·간판 기반 추정) 우선, 없으면 인허가 업종. 위에서부터 처음 맞는 묶음.
GROUPS = [
    ("카페·찻집", ["카페", "커피", "다방", "찻집", "베이커리", "디저트", "아이스크림", "도넛", "와플", "스무디", "과자", "만화방", "만화", "스터디", "방탈출", "보드게임", "베이글"]),
    ("술집·주점", ["술집", "호프", "주점", "포차", "포장마차", "정종", "대포", "소주", "펍", "오뎅바", "이자카야", "바", "맥주", "위스키", "요리주점", "감성주점", "맥주축제"]),
    ("게임·오락", ["PC방", "인터넷컴퓨터", "게임", "당구", "노래", "오락", "플스", "멀티방", "VR", "라이브"]),
    ("미용·건강", ["미용", "네일", "피부", "왁싱", "메이크업", "이발", "이용업", "헬스", "체력", "필라테스", "치과", "안경", "약국"]),
    ("숙박", ["숙박", "여관", "고시원", "쉐어하우스", "파티룸"]),
    ("패스트푸드·분식", ["패스트푸드", "햄버거", "분식", "떡볶이", "김밥", "도시락", "라면", "치킨", "통닭", "피자", "튀김", "샌드위치", "포케", "샐러드"]),
    ("고기·구이", ["고깃", "갈비", "고기", "곱창", "대창", "숯불", "삼겹", "족발", "보쌈", "양꼬치", "양고기", "바비큐", "주물럭", "불백", "식육", "닭갈비", "닭발", "장어", "조개구이", "생선구이", "꼬치"]),
    ("중식", ["중국", "중식", "마라", "짜장", "탕수"]),
    ("일식", ["일식", "횟집", "초밥", "라멘", "우동", "돈까스", "규카츠", "텐동", "덮밥"]),
    ("양식·외국음식", ["외국음식", "인도", "태국", "베트남", "네팔", "멕시칸", "케밥", "쌀국수", "지중해", "양식", "경양식", "레스토랑", "파스타", "스테이크", "뷔페"]),
    ("한식", ["한식", "국밥", "찌개", "국수", "칼국수", "냉면", "탕", "찜", "순두부", "설렁", "뚝배기", "막국수", "반찬", "식당", "일반조리", "해물", "동태", "만두", "철판"]),
]
OTHER = "기타·소매·서비스"

def group_of(r):
    for text in ((r.get("category_ai") or ""), (r.get("category") or "")):
        if not text: continue
        for g, kws in GROUPS:
            if any(k in text for k in kws): return g
    return OTHER

def _t(s):
    """'YYYY-MM-DD' 또는 'YYYY-MM' → 연 단위 실수. 없으면 None."""
    m = re.match(r"(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?", s or "")
    if not m: return None
    y, mo, d = int(m.group(1)), int(m.group(2) or 7), int(m.group(3) or 1)
    try: return y + (date(y, mo, min(d, 28)).timetuple().tm_yday - 1) / 365.25
    except ValueError: return float(y)

def _pct(xs, q):
    xs = sorted(xs)
    if not xs: return None
    k = (len(xs) - 1) * q; f = int(k); c = min(f + 1, len(xs) - 1)
    return xs[f] + (xs[c] - xs[f]) * (k - f)

def delay_assumption(rows):
    """관측이 있고 폐업일 기록이 있는 업소에서, 기록이 마지막 영업 관측보다 얼마나 늦는지(조사 간격을 포함한 상한)의 75백분위.
    관측 없는 업소의 실제 폐업이 기록보다 이만큼 빠를 수 있다고 가정하는 값이다."""
    ds = []
    for r in rows:
        if r.get("source") == "로드뷰 직접 조사" or "seen_after_close" in r.get("flags", ""): continue
        e, sl = _t(r.get("end")), _t(r.get("sign_last"))
        sm = _t(r.get("semas_last"))                                     # 공공 상가정보 스냅샷의 마지막 영업 관측(폐업 기록 1년 이내인 것만 같은 업소로 본다)
        if sm is not None and e is not None and sm <= e + 1.0 and (sl is None or sm > sl): sl = min(sm, e)
        if e is not None and sl is not None and r.get("end_basis") == "폐업일" and not r.get("end_before"): ds.append(max(0.0, e - sl))
    return (_pct(ds, 0.75) or 0.0), ds

def delay_ci(ds, q=0.75, B=500, seed=0):
    """지연 상한의 q 백분위를 부트스트랩으로 다시 구해 90% 구간을 낸다(표본이 작아 값이 얼마나 흔들리는지 보여 주려는 것)."""
    import random
    if len(ds) < 5: return None
    rng = random.Random(seed)
    vals = sorted(_pct([rng.choice(ds) for _ in ds], q) for _ in range(B))
    return [round(vals[int(B * 0.05)], 1), round(vals[int(B * 0.95)], 1)]

def prepare(rows, delay):
    """행마다 시작·종료 구간과 근거 등급을 붙인 사본 목록."""
    out = []
    for r in rows:
        s = _t(r.get("start"))
        if s is None: continue
        flags = r.get("flags", "")
        sign_only = r.get("source") == "로드뷰 직접 조사"
        e_rec, sl, eb, sa = _t(r.get("end")), _t(r.get("sign_last")), _t(r.get("end_before")), _t(r.get("start_after"))
        x = {"id": r["id"], "jibun": r["jibun"], "name": r["name"], "floor": r.get("floor", ""), "group": group_of(r),
             "s": s, "s_lo": min(sa, s) if sa is not None else s, "flags": flags, "note": ""}
        if sign_only:
            if eb is None:                                   # 마지막 조사까지 간판이 있었다 → 영업 중
                x.update(state="open", e_lo=sl, e_hi=T_NOW, ev=EV_OBS)
            else:
                x.update(state="closed", e_lo=sl, e_hi=eb)
        elif not r.get("end") and r.get("semas_last"):                  # 공공 상가정보 스냅샷에서 영업 중이 확인됨: 갱신 흔적이 없던 행도 영업 중으로 본다
            x.update(state="open", e_lo=max(s, _t(r["semas_last"])), e_hi=T_NOW, ev=EV_OBS)
        elif not r.get("end"):
            if r.get("end_basis") in ("폐업", "취소/말소/만료/정지/중지"):   # 폐업은 했는데 날짜가 없다
                x.update(state="undated", e_lo=s, e_hi=T_NOW, ev=EV_REC)
            elif "stale_open" in flags:                      # 기록상 영업 중이나 갱신 흔적이 없다
                x.update(state="stale", e_lo=s, e_hi=T_NOW, ev=EV_REC)
            else:
                x.update(state="open", e_lo=max(s, sl or s), e_hi=T_NOW, ev=EV_OBS if sl else EV_REC)
        else:
            hi = min(e_rec, eb) if eb is not None else e_rec
            sm = _t(r.get("semas_last"))                                # 상가정보 스냅샷 마지막 관측도 영업 중이었다는 하한이다
            if sm is not None and (sl is None or sm > sl) and sm <= hi + 1.0: sl = min(sm, hi)
            if sl is not None:
                lo = sl
                if lo > hi: lo = hi; x["note"] = "기록상 폐업 이후에도 간판이 관측됨"
                x.update(state="closed", e_lo=lo, e_hi=hi)
            else:
                x.update(state="closed", e_lo=max(s, hi - delay), e_hi=hi, ev=EV_REC)
        if x["state"] == "closed" and "ev" not in x:
            x["ev"] = EV_OBS if x["e_hi"] - x["e_lo"] <= WIDTH_OK else EV_PART
        out.append(x)
    return out

# ---------- 생존분석(Kaplan–Meier, 우측 중도절단) ----------
def km(durs):
    """durs: [(기간, 종료 관측 여부)]. 반환: 계단 곡선 [(t, S)] (t 오름차순)."""
    ev = sorted(durs); n = len(ev); S = 1.0; curve = []; i = 0
    while i < len(ev):
        t = ev[i][0]; d = c = 0
        while i < len(ev) and ev[i][0] == t:
            d += ev[i][1]; c += 1 - ev[i][1]; i += 1
        if d: S *= 1 - d / n; curve.append((t, S))
        n -= d + c
    return curve

def surv_at(curve, t):
    S = 1.0
    for ts, s in curve:
        if ts <= t: S = s
        else: break
    return S

def median_of(curve):
    for t, s in curve:
        if s <= 0.5: return t
    return None

def survival_group(items):
    """items: prepare() 결과 중 종료 시점을 알 수 있는 행. 하한·상한 두 곡선."""
    lo, hi = [], []
    for x in items:
        if x["state"] == "closed":
            lo.append((max(0.0, x["e_lo"] - x["s"]), 1)); hi.append((max(0.0, x["e_hi"] - x["s_lo"]), 1))
        else:                                                    # 영업 중: 중도절단
            c = max(0.0, T_NOW - x["s"]); lo.append((c, 0)); hi.append((c, 0))
    cl, ch = km(lo), km(hi)
    ml, mh = median_of(cl), median_of(ch)
    return {"n": len(items), "n_closed": sum(1 for x in items if x["state"] == "closed"),
            "at": {str(t): sorted([round(surv_at(cl, t), 2), round(surv_at(ch, t), 2)]) for t in SURVIVAL_T},     # 두 곡선은 중도절단 때문에 드물게 교차하므로 작은 쪽·큰 쪽으로 낸다
            "median": [None if ml is None else round(ml, 1), None if mh is None else round(mh, 1)]}

# ---------- 구성 ----------
def composition(items):
    """연도별로 '확실히 영업 중'(그 해 전체를 덮음)과 '영업 중일 수 있음'(걸침) 수를 업종 묶음별로."""
    years = [y for y in CORE_YEARS if any(x["s"] <= y + 1 for x in items)]
    rows = {}
    for y in years:
        cnt = {}
        for x in items:
            if x["state"] in ("undated",): lo_cert, possible = False, x["s"] <= y + 1
            else:
                possible = x["s"] <= y + 1 and x["e_hi"] >= y
                lo_cert = x["s_lo"] <= y and x["e_lo"] >= y + 1 if x["state"] == "closed" else (x["s"] <= y and x["state"] == "open")
            if possible:
                c = cnt.setdefault(x["group"], [0, 0]); c[1] += 1; c[0] += 1 if lo_cert else 0
        rows[y] = cnt
    out = {"years": years, "by_year": {str(y): {g: v for g, v in sorted(c.items(), key=lambda kv: -kv[1][1])} for y, c in rows.items()},
           "total": {str(y): [sum(v[0] for v in c.values()), sum(v[1] for v in c.values())] for y, c in rows.items()}}
    out["change"] = [ch for ch in (composition_change(out, 2015, 2025), composition_change(out, 2005, 2025)) if ch]
    return out

def composition_change(C, y0, y1):
    """두 시점 사이 업종별 업소 수 변화. 증감 범위 = [끝 시점 '확실' − 시작 시점 '가능', 끝 시점 '가능' − 시작 시점 '확실'].
    범위가 0을 포함하지 않으면 방향이 확실한 증가·감소, 포함하면 방향 불확실이다."""
    if y0 not in C["years"] or y1 not in C["years"]: return None
    a, b = C["by_year"][str(y0)], C["by_year"][str(y1)]
    items = []
    for g in set(a) | set(b):
        s0, e0 = a.get(g, [0, 0]), b.get(g, [0, 0])
        lo, hi = e0[0] - s0[1], e0[1] - s0[0]
        items.append({"group": g, "from": s0, "to": e0, "delta": [lo, hi], "mid": (lo + hi) / 2, "dir": "증가" if lo > 0 else "감소" if hi < 0 else "불확실"})
    items.sort(key=lambda x: -abs(x["mid"]))
    t0, t1 = C["total"][str(y0)], C["total"][str(y1)]
    return {"from": y0, "to": y1, "items": items, "total_delta": [t1[0] - t0[1], t1[1] - t0[0]],
            "most_up": max(items, key=lambda x: x["mid"])["group"] if items else None, "most_down": min(items, key=lambda x: x["mid"])["group"] if items else None}

# ---------- 자리 이력 ----------
def history(items, max_parcels=60):
    byp = {}
    for x in items: byp.setdefault(x["jibun"], []).append(x)
    parcels, intervals, gaps = [], [], []
    for j, xs in sorted(byp.items()):
        xs = sorted(xs, key=lambda x: (x["s"], x["name"]))
        entries = [{"name": x["name"], "floor": x["floor"], "group": x["group"], "start": round(x["s"], 1), "end": None if x["state"] in ("open", "stale") else [round(x["e_lo"], 1), round(x["e_hi"], 1)],
                    "state": x["state"], "evidence": x["ev"]} for x in xs]
        for a, b in zip(xs, xs[1:]):
            same = (not a["floor"] or not b["floor"] or a["floor"] == b["floor"])
            if not same: continue                                 # 다른 층이면 교체가 아니다
            intervals.append(b["s"] - a["s"])
            if a["state"] == "closed":
                gaps.append((b["s"] - a["e_hi"], b["s"] - a["e_lo"]))
        parcels.append({"jibun": j, "n": len(xs), "floors_known": all(x["floor"] for x in xs), "entries": entries})
    shown = sorted(parcels, key=lambda p: -p["n"])[:max_parcels]
    ov = [g for g in gaps if g[1] < 0]                            # 후속 개업이 이전 업소의 영업 중에 시작(같은 건물 안 공존 가능)
    pos = [g for g in gaps if g[1] >= 0]
    return {"n_parcels": len(parcels), "n_turnovers": len(intervals),
            "interval_median": round(statistics.median(intervals), 1) if len(intervals) >= 3 else None,
            "gap_range_median": ([round(statistics.median(g[0] for g in pos), 1), round(statistics.median(g[1] for g in pos), 1)] if len(pos) >= 3 else None),
            "overlap_share": round(len(ov) / len(gaps), 2) if gaps else None, "n_gaps": len(gaps),
            "parcels": shown, "truncated": len(parcels) - len(shown)}

# ---------- 리포트 ----------
def report(rows, parcels, jibuns, focus=None):
    """rows: agent.load_db()의 행, parcels: 필지 사전, jibuns: 영역에 든 필지 지번 목록. focus: 'survival'|'composition'|'history'|None."""
    delay, delays = delay_assumption(rows)                          # 가정은 영역과 무관하게 전체 관측 업소로 구한다
    sel = set(jibuns)
    items = prepare([r for r in rows if r["jibun"] in sel], delay)
    n = len(items)
    ev = {k: sum(1 for x in items if x["ev"] == k) for k in (EV_OBS, EV_PART, EV_REC)}
    core = sum(1 for j in sel if parcels.get(j, {}).get("core")); ring = sum(1 for j in sel if j in parcels and not parcels[j].get("core"))
    st = {k: sum(1 for x in items if x["state"] == k) for k in ("open", "closed", "stale", "undated")}
    overview = {"n_parcels": len(sel), "core_parcels": core, "ring_parcels": ring, "n_shops": n, "evidence": ev, "state": st,
                "period": [round(min(x["s"] for x in items)), min(2026, round(max(x["e_hi"] if x["state"] == "closed" else x["s"] for x in items)))] if items else None,
                "seen_after_close": sum(1 for x in items if x["note"]), "enough": n >= MIN_N}
    # 영업 기간: 종료를 알 수 있는 행(영업 중·폐업). 갱신 흔적 없는 '영업 중'과 날짜 없는 폐업은 제외
    usable = [x for x in items if x["state"] in ("open", "closed")]
    gr = {}
    for x in usable: gr.setdefault(x["group"], []).append(x)
    surv = {"groups": [], "insufficient": [], "excluded": st["stale"] + st["undated"], "delay_years": round(delay, 1)}
    if len(usable) >= MIN_N:
        surv["all"] = survival_group(usable)
        sel_rows = [r for r in rows if r["jibun"] in sel]
        grid = sorted({0.0, round(_pct(delays, 0.5) or 0.0, 1), round(delay, 1), 3.0})     # 지연 가정을 바꿔 보았을 때 결론이 얼마나 달라지는가
        surv["sensitivity"] = []
        for d in grid:
            g = survival_group([x for x in prepare(sel_rows, d) if x["state"] in ("open", "closed")])
            surv["sensitivity"].append({"delay": d, "at5": g["at"]["5"], "median": g["median"]})
    for g, xs in sorted(gr.items(), key=lambda kv: -len(kv[1])):
        if len(xs) >= MIN_N: surv["groups"].append({"group": g, **survival_group(xs)})
        else: surv["insufficient"].append({"group": g, "n": len(xs)})
    rep = {"focus": focus, "overview": overview,
           "composition": composition(items) if items else None,
           "survival": surv if len(usable) >= MIN_N else {"insufficient_all": True, "n": len(usable), "excluded": surv["excluded"]},
           "history": history(items) if items else None,
           "limits": {"basis": "인허가 기록과 로드뷰 간판 관측 기준", "min_n": MIN_N, "delay_years": round(delay, 1), "delay_n": len(delays), "delay_ci": delay_ci(delays),
                      "notes": ["폐업 신고에는 법정 기한이 없어 기록상 폐업일은 실제 폐업보다 늦을 수 있다(식품위생법 제37조, 2026-11 현행 확인).",
                                f"관측이 없는 업소({ev[EV_REC]}곳)는 실제 폐업이 기록보다 최대 {delay:.1f}년 빠를 수 있다고 가정했다(관측 있는 업소 {len(delays)}곳의 지연 상한 75백분위" + (f", 표본이 작아 부트스트랩 90% 구간은 {delay_ci(delays)[0]}–{delay_ci(delays)[1]}년" if delay_ci(delays) else "") + "). 이 가정을 바꾼 결과는 영업 기간 섹션에 함께 보인다.",
                                f"로드뷰 조사는 {region.R['core_name']} 구간에만 있고 반경 150m 확장 구간은 인허가 기록만이다.",
                                "2011년 이전 기록에는 옛 조문이 적용됐을 수 있다.", "예측·추천은 하지 않고 기록된 이력만 설명한다."]}}
    return rep


# ---------- AI 해설용 사실 목록 ----------
def _rg(a, unit=""):
    return f"{a[0]}{unit}" if a[0] == a[1] else f"{a[0]}–{a[1]}{unit}"

def facts(rep):
    """리포트의 수치를 한 줄짜리 사실(F0, F1…)로 풀어 쓴다. AI는 이 목록의 숫자만 쓸 수 있고, 코드가 서술 속 숫자를 이 목록과 대조한다."""
    out = []
    add = lambda t: out.append((f"F{len(out)}", t))
    o = rep["overview"]
    if not o["n_shops"]: return out
    ev = o["evidence"]
    add(f"영역: 필지 {o['n_parcels']}개({region.R['core_name']} {o['core_parcels']}개, 주변 {o['ring_parcels']}개), 업소 {o['n_shops']}곳, 기록 기간 {o['period'][0]}~{o['period'][1]}년. "
        f"영업 중 {o['state']['open']}곳, 폐업 {o['state']['closed']}곳, 종료 시점 불명 {o['state']['stale'] + o['state']['undated']}곳. "
        f"근거 등급: 관측 확인 {ev[EV_OBS]}곳, 부분 관측 {ev[EV_PART]}곳, 기록만 {ev[EV_REC]}곳.")
    C = rep.get("composition")
    if C:
        for y in C["years"]:
            gs = list(C["by_year"][str(y)].items())[:8]
            add(f"{y}년 영업 중 업소 수(확실–가능): 합계 {_rg(C['total'][str(y)], '곳')}; " + ", ".join(f"{g} {_rg(v, '곳')}" for g, v in gs))
    for ch in (C or {}).get("change", []):
        sg = lambda d: f"{d[0]:+d}~{d[1]:+d}곳"
        add(f"업종 변화 {ch['from']}년→{ch['to']}년(증감 범위: 끝 시점 확실−시작 시점 가능 ~ 끝 시점 가능−시작 시점 확실, 범위가 0을 포함하면 방향 불확실). 전체 {sg(ch['total_delta'])}. "
            + ", ".join(f"{x['group']} {x['from'][0]}–{x['from'][1]}곳→{x['to'][0]}–{x['to'][1]}곳({sg(x['delta'])}, {x['dir'] if x['dir'] != '불확실' else '방향 불확실'})" for x in ch["items"][:7])
            + f". 범위 중앙값 기준 가장 크게 는 업종 {ch['most_up']}, 가장 크게 준 업종 {ch['most_down']}.")
    V = rep["survival"]
    if V.get("insufficient_all"):
        add(f"영업 기간: 종료 시점을 아는 업소가 {V['n']}곳뿐이라 표본 부족(기준 {MIN_N}곳)으로 수치를 내지 않았다.")
    else:
        def line(name, g):
            m = g["median"]; med = "50% 넘게 영업 중이라 중앙값 없음" if m[0] is None and m[1] is None else f"{m[0] if m[0] is not None else '?'}–{m[1] if m[1] is not None else '?'}년"
            return f"{name}: 표본 {g['n']}곳(폐업 {g['n_closed']}곳), 3년 생존 {_rg([round(x * 100) for x in g['at']['3']], '%')}, 5년 생존 {_rg([round(x * 100) for x in g['at']['5']], '%')}, 10년 생존 {_rg([round(x * 100) for x in g['at']['10']], '%')}, 영업 기간 중앙값 {med}"
        add("영업 기간(기록 기준, 범위는 폐업 시점 불확실성 반영) " + line("전체", V["all"]))
        for g in V["groups"]: add("영업 기간 " + line(g["group"], g))
        if V["insufficient"]: add("표본 부족으로 수치 없음: " + ", ".join(f"{x['group']} {x['n']}곳" for x in V["insufficient"]))
        if V.get("sensitivity"):
            add("지연 가정을 바꿨을 때 전체 5년 생존 범위: " + ", ".join(f"지연 {x['delay']}년이면 {_rg([round(v * 100) for v in x['at5']], '%')}" for x in V["sensitivity"]) + ". 가정을 바꿔도 범위가 크게 흔들리지 않으면 결론이 가정에 덜 의존한다.")
        add(f"영업 기간 계산에서 종료 시점 불명 {V['excluded']}곳은 제외했다. 관측 없는 업소의 실제 폐업은 기록보다 최대 {V['delay_years']}년 빠를 수 있다고 가정했다.")
    H = rep.get("history")
    if H:
        t = f"자리 이력: 같은 자리 업소 교체 {H['n_turnovers']}건"
        if H["interval_median"] is not None: t += f", 개업 간격 중앙값 {H['interval_median']}년"
        if H["gap_range_median"]: t += f", 폐업~다음 개업 공백 중앙값 {_rg(H['gap_range_median'], '년')}"
        if H["overlap_share"] is not None: t += f", 다음 업소가 이전 업소 폐업 전에 개업한 경우 {round(H['overlap_share'] * 100)}%(호실 정보가 없어 같은 건물의 다른 호실일 수 있음)"
        add(t + ".")
    return out
