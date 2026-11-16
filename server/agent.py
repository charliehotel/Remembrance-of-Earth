"""대지의 기억 에이전트: 흐릿한 기억 단서 → 후보 장소·상호 + 근거. 대화를 이어 가며 범위를 조절한다.

한 번의 질문에서 하는 일
  1. 단서 해석(Liner Model): 질문과 이전 대화에서 시기·업종·상호 조각·층·위치를 추려 낸다.
  2. 정확 검색(코드): 질문에 적힌 조건 그대로 내부 이력에서 찾는다.
  3. 확장 검색(코드): 기억이 틀렸을 수 있으니 시기(±2년)와 위치(반경 50m)를 넓혀 다시 찾는다. 정확 결과는 위에, 확장 결과는 아래에 둔다.
  4. 웹 검색(Liner Search): 정확 결과가 약하거나 사용자가 원하면 웹에서도 찾는다. 사용했는지 항상 표시한다.
  5. 판정(Liner Model): 근거를 대조해 확인 / 추정 / 미확인으로 구분한다. 근거 없는 내용은 만들지 않는다.
상태(state)는 서버에 저장하지 않고 화면이 들고 다니며, 질문마다 다시 보낸다."""
import csv, math, re
from pathlib import Path
import liner

DATA = Path(__file__).resolve().parent.parent / "data"
EXPAND_YEARS, EXPAND_RADIUS_M, MAX_LEVEL = 2, 50, 3     # 확장 단계(level)마다 ±2년·반경 50m씩 넓어진다

# ---------- 데이터 ----------
def load_db():
    """연세로12길 구간(timeline_businesses.csv)과 반경 150m 확장 구간(timeline_businesses_r150.csv)을 함께 읽는다.
    parcels 에는 확장 구간 필지도 들어 있다(core=False). 기본 위치(center)는 연세로12길 구간 필지만으로 계산한다."""
    rows = list(csv.DictReader(open(DATA / "timeline_businesses.csv", encoding="utf-8-sig")))
    parcels = {r["jibun"]: dict(r, core=True) for r in csv.DictReader(open(DATA / "parcels.csv", encoding="utf-8-sig"))}
    ring = DATA / "timeline_businesses_r150.csv"
    if ring.exists():
        rows += list(csv.DictReader(open(ring, encoding="utf-8-sig")))
        for r in csv.DictReader(open(DATA / "parcels_r150.csv", encoding="utf-8-sig")):
            parcels.setdefault(r["jibun"], dict(r, anchor="", core=False))
    for i, r in enumerate(rows):
        r["id"] = f"D{i}"
        p = parcels.get(r["jibun"])
        r["lon"], r["lat"] = (float(p["lon"]), float(p["lat"])) if p else (None, None)
    return rows, parcels

def _ym(s, default):
    m = re.match(r"(\d{4})(?:-(\d{2}))?", s or "")
    return int(m.group(1)) + (int(m.group(2) or 6) - 1) / 12 if m else default

def _dist_m(a, b):
    (lo1, la1), (lo2, la2) = a, b
    dx = (lo2 - lo1) * 111320 * math.cos(math.radians((la1 + la2) / 2)); dy = (la2 - la1) * 110574
    return math.hypot(dx, dy)

def resolve_anchor(text, parcels):
    """위치 표현 → (좌표, 설명). 지번이나 랜드마크 이름이면 그 필지, 아니면 연세로12길 중심."""
    core = [p for p in parcels.values() if p.get("core")] or list(parcels.values())
    center = (sum(float(p["lon"]) for p in core) / len(core), sum(float(p["lat"]) for p in core) / len(core))
    t = (text or "").replace(" ", "")
    if t:
        for j, p in parcels.items():
            if j == t.replace("창천동", "") or (p["anchor"] and (p["anchor"].replace(" ", "") in t or t in p["anchor"].replace(" ", ""))):
                return (float(p["lon"]), float(p["lat"])), (p["anchor"] or f"창천동 {j}"), True
        for tok in re.findall(r"\d+-\d+", t):
            if tok in parcels: return (float(parcels[tok]["lon"]), float(parcels[tok]["lat"])), f"창천동 {tok}", True
    return center, "연세로12길", False

# ---------- 1. 단서 해석 ----------
CLUE_SCHEMA = {"type": "object", "additionalProperties": False,
    "required": ["reset", "accept_suggestion", "reject_top", "year_from", "year_to", "categories", "name_hints", "floor", "anchor", "radius_m", "widen", "web", "summary"],
    "properties": {
        "reset": {"type": "boolean"}, "accept_suggestion": {"type": "boolean"}, "reject_top": {"type": "boolean"}, "year_from": {"type": "integer"}, "year_to": {"type": "integer"},
        "categories": {"type": "array", "items": {"type": "string"}},
        "name_hints": {"type": "array", "items": {"type": "string"}},
        "floor": {"type": "string"}, "anchor": {"type": "string"}, "radius_m": {"type": "integer"},
        "widen": {"type": "string", "enum": ["none", "wider", "narrower"]},
        "web": {"type": "string", "enum": ["auto", "force", "skip"]}, "summary": {"type": "string"}}}

def parse_clue(text, prev, pending=None):
    sys = ("사용자가 기억 속 가게를 설명하거나, 이전 결과에 대해 후속 요청을 한다. 현재 해석(prev)이 주어지면 새 메시지를 반영해 갱신한다: "
           "사용자가 바꾼 항목만 바꾸고 나머지는 유지한다. 완전히 다른 가게를 찾는 새 질문이면 reset=true로 하고 이전 값을 버린다. "
           "accept_suggestion(직전에 에이전트가 한 제안(pending)을 사용자가 받아들이면 true: '응', '네', '그렇게 해줘' 등. 제안이 없거나 다른 요청이면 false), reject_top(사용자가 직전 답변의 1순위 후보가 아니라고 하면 true: '거기가 아닌 것 같아', '그 가게는 아니야' 등), 필드: year_from/year_to(말한 시기, 한 해만 말했으면 둘 다 같은 해, 모르면 1992와 2026), categories(업종 키워드를 짧은 단어 단위로 2~5개(두 글자 이상): 예 '인도 카레집'이면 인도, 카레, 커리. 한식, 호프, 카페, 미용 등. 구절 통째로 넣지 않는다), "
           "name_hints(기억한 상호의 일부 글자), floor(층, 예 '1층', 모르면 빈 문자열), anchor(위치 표현: 지번이나 '창천감리교회'·'아웃백' 같은 랜드마크, 없으면 빈 문자열), "
           "radius_m(반경을 말했을 때만 m, 아니면 0), widen(이번 메시지에서 한 요청만 반영하고 prev의 값은 따르지 않는다. '범위 넓혀줘'·'더 멀리'면 wider, '좁혀줘'·'정확히'면 narrower, 아니면 none), "
           "web(이번 메시지만 기준: 웹에서도 찾아 달라 하면 force, 웹은 쓰지 말라면 skip, 아니면 auto), summary(해석 한 문장). 말하지 않은 값을 추측하지 않는다.")
    user = f"현재 해석(prev): {prev if prev else '없음'}\n직전 제안(pending): {pending['text'] if pending else '없음'}\n새 메시지: {text}"
    return liner.chat_json(sys, user, CLUE_SCHEMA, "clue", 500)

# ---------- 2·3. 정확 / 확장 검색 ----------
SYN = {"인도": ["인도", "네팔", "커리", "카레", "탄두리", "naan"], "카레": ["카레", "커리", "인도"], "커리": ["커리", "카레", "인도"],
       "호프": ["호프", "통닭", "맥주", "주점", "소주방", "대포"], "카페": ["카페", "커피", "다방", "휴게음식점", "제과"],
       "분식": ["분식", "떡볶이", "김밥"], "미용": ["미용", "헤어", "머리"], "중식": ["중식", "중국", "짜장", "마라"], "일식": ["일식", "초밥", "라멘", "일본"],
       "양식": ["양식", "경양식", "스테이크", "파스타", "피자"], "치킨": ["치킨", "통닭", "닭"], "술집": ["술", "주점", "호프", "포장마차", "소주방"]}

def cat_terms(cats):
    """업종 표현 → 검색 키워드 집합. '인도 카레집' 같은 구절도 단어와 동의어로 나눠 맞춘다."""
    out = set()
    for c in cats:
        c = (c or "").strip()
        if not c: continue
        out.add(c.replace(" ", ""))
        for tok in re.split(r"[\s·,/()]+", c):
            tok = re.sub(r"(집|점|가게|전문점)$", "", tok)
            if len(tok) >= 2:                                                      # 한 글자 단어는 오탐이 많아 제외
                out.add(tok)
                out.update(SYN.get(tok, []))
    return {t.lower() for t in out if t}

def _text(r): return " ".join([r["name"], r["category"], r["license_type"], r["observed_as"], r.get("category_ai", "")])   # category_ai 는 AI 추정 업종(비공식)

def _hint_score(h, r):
    h = h.replace(" ", "")
    if not h: return 0, False
    if h.lower() in _text(r).replace(" ", "").lower(): return 4, True
    return 0.5 * sum(ch in r["name"] for ch in set(h)) / len(set(h)), False

def row_key(r): return f"{r['jibun']}|{r['name']}|{r['start']}"

def search_tiers(db, parcels, clue, level, rejected=(), nearby=False):
    y0, y1 = clue["year_from"], clue["year_to"] + 1
    anchor_pt, anchor_name, anchored = resolve_anchor(clue["anchor"], parcels)
    r_exact = clue["radius_m"] or (30 if anchored else None)                       # 위치를 말했으면 그 근처, 아니면 제한 없음
    r_wide = max(EXPAND_RADIUS_M * (level + 1), (r_exact or 0)) if (anchored or clue["radius_m"]) else None
    margin = EXPAND_YEARS * (level + 1)
    exact, wide = [], []
    terms = cat_terms(clue["categories"])
    for r in db:
        if row_key(r) in rejected: continue                                        # 사용자가 '아니다'라고 한 후보는 제외
        s, e = _ym(r["start"], 1992), _ym(r["end"], 2026.9)
        d = _dist_m(anchor_pt, (r["lon"], r["lat"])) if r["lon"] else None
        in_exact_years = not (e < y0 or s > y1)
        in_wide_years = not (e < y0 - margin or s > y1 + margin)
        if not in_wide_years: continue
        text = _text(r).replace(" ", "").lower()
        cat_ok = (not terms) or any(t in text for t in terms)
        hint_pts, hint_all = 0, True
        for h in clue["name_hints"]:
            pts, full = _hint_score(h, r); hint_pts += pts; hint_all &= full
        fl = clue["floor"].replace("층", "") if clue["floor"] else ""
        floor_known = bool(r["floor"] or "층" in r["observed_as"])
        floor_ok = (not fl) or (floor_known and (r["floor"] == fl or f"{fl}층" in r["observed_as"]))
        sc = 1.0 + hint_pts + (2 if cat_ok and terms else 0) + (1 if fl and floor_ok else 0) + (0.5 if r["grade"] == "A" else 0)
        sc -= 0 if in_exact_years else 1.0                                          # 시기를 벗어나면 감점
        is_exact = in_exact_years and cat_ok and hint_all and floor_ok and (r_exact is None or (d is not None and d <= r_exact))
        row = dict(r, score=round(sc, 2), dist_m=None if d is None else round(d))
        if is_exact: exact.append(row)
        else:
            if r_wide is not None and (d is None or d > r_wide): continue
            if not nearby:
                if not clue["categories"] and not clue["name_hints"]: continue     # 조건이 없으면 확장해도 의미가 없다
                if terms and not cat_ok and hint_pts < 2: continue     # 업종도 상호도 안 맞으면 제외
            wide.append(row)
    dkey = lambda x: (-x["score"], x["dist_m"] if x["dist_m"] is not None else 1e9)   # 점수가 같으면 기준 위치에 가까운 순
    exact.sort(key=dkey); wide.sort(key=dkey)
    scope = {"years": [y0, y1 - 1], "wide_years": [y0 - margin, y1 - 1 + margin], "radius_exact": r_exact, "radius_wide": r_wide,
             "anchor": anchor_name if (anchored or clue["radius_m"]) else None, "level": level, "nearby": nearby, "rejected": len(rejected)}
    return [dict(x, tier="exact") for x in exact[:5]], [dict(x, tier="wide") for x in wide[:5]], scope

# ---------- 4. 웹 검색 ----------
def gather_web(clue, exact, wide, n_each=4, max_queries=5):
    ev, seen, queries = [], set(), []
    place = "신촌 연세로12길"
    if clue["name_hints"] or clue["categories"]:
        queries.append(" ".join([place, str(clue["year_from"]) + "년" if clue["year_from"] > 1992 else "", *clue["categories"], *clue["name_hints"]]).strip())
    for c in (exact + wide)[:3]:
        if c["name"] not in ("상호", "상호판독보류"): queries.append(f"{c['name']} 창천동 신촌 {c['category'] or c.get('category_ai') or (clue['categories'][0] if clue['categories'] else '')}".strip())
    for q in queries[:max_queries]:
        for x in liner.search(q, n_each):
            if x["url"] in seen: continue
            seen.add(x["url"]); x["id"] = f"W{len(ev)}"; x["query"] = q; ev.append(x)
    return ev, queries[:max_queries]

def web_decision(clue, exact):
    if clue["web"] == "skip": return False, "사용자가 웹 검색을 원하지 않음"
    if clue["web"] == "force": return True, "사용자가 웹 검색을 요청함"
    if not exact: return True, "정확히 맞는 내부 기록이 없어 웹에서 보완"
    if max(c["score"] for c in exact) < 6: return True, "정확 결과의 근거가 약해 웹으로 교차 확인"
    return False, "내부 기록만으로 충분히 일치해 웹 검색은 쓰지 않음"

# ---------- 5. 판정 ----------
JUDGE_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["judgements", "leads", "answer", "follow_ups"],
    "properties": {
      "judgements": {"type": "array", "items": {"type": "object", "additionalProperties": False,
        "required": ["id", "verdict", "confidence", "reason", "evidence_ids"],
        "properties": {"id": {"type": "string"}, "verdict": {"type": "string", "enum": ["확인", "추정", "미확인"]},
          "confidence": {"type": "number"}, "reason": {"type": "string"},
          "evidence_ids": {"type": "array", "items": {"type": "string"}}}}},
      "leads": {"type": "array", "items": {"type": "object", "additionalProperties": False,
        "required": ["name", "why", "evidence_ids"],
        "properties": {"name": {"type": "string"}, "why": {"type": "string"},
                       "evidence_ids": {"type": "array", "items": {"type": "string"}}}}},
      "answer": {"type": "string"},
      "follow_ups": {"type": "array", "items": {"type": "string"}}}}

def judge(text, clue, cands, ev, web_used, rejected=()):
    sys = ("너는 도시 기록 검증 에이전트다. 사용자의 기억 단서와 내부 이력 후보(D로 시작, tier는 '정확'=질문 조건과 그대로 일치, '확장'=시기·위치를 넓혀 찾은 것), "
           "웹 검색 근거(W로 시작)가 주어진다. 각 후보가 단서에 맞는지 판정하라. 규칙: (1) 주어진 자료에 없는 사실은 쓰지 않는다. "
           "(2) 웹에서 찾지 못한 것은 반증이 아니다. 웹 근거가 없다는 이유로 내부 인허가 일치를 깎지 않는다(근거가 웹에 없음을 reason에 밝힐 뿐). verdict '확인'은 단서의 시기·업종·층이 내부 이력과 일치하고, 인허가 기록(등급 A는 공공 인허가 기록이므로 그 자체가 근거) 또는 웹 근거가 뒷받침할 때. "
           "상호 조각까지 맞으면 확신을 높인다. 일부만 맞으면 '추정', 근거가 없거나 충돌하면 '미확인'. 확장 tier는 시기나 위치가 어긋난다는 점을 reason에 밝힌다. "
           "(3) reason은 무엇이 일치·충돌하는지 100자 이내로, id(D·W 번호)와 'tier'라는 말 대신 상호명과 '정확 조건'·'넓힌 범위' 같은 표현을 쓴다. (4) evidence_ids는 주어진 W·D id만. "
           "(5) 웹 근거에서 내부 후보에 없는 새 상호가 단서와 맞아 보이면 leads에 넣는다. name에는 상호만, 설명은 why에. 단서와 실제로 맞는 경우에만 넣고, 맞지 않는 곳은 아예 넣지 않는다(불일치를 설명하려고 넣지 말 것). 항상 미검증이다. "
           "(5-1) 후보의 'AI추정업종'은 공식 인허가 업종이 아니라 상호나 웹 검색으로 AI가 추정한 값이다. 업종 일치를 판단할 때 참고는 하되, 공식 업종보다 약한 근거로 다루고, 업종 일치를 이 값에 의존했다면 reason과 answer에 '업종은 AI가 상호로 추정한 것이라 정확하지 않을 수 있다'고 밝힌다. 공식 업종과 AI 추정이 다르면 공식 업종을 우선한다. "
           "(6) answer는 사용자에게 보일 2문장 요약. 정확 결과가 있으면 그것을 먼저 말하고, 확신이 낮으면 그렇게 말한다. 웹 검색을 쓰지 않았다면 쓰지 않았다고 사실대로 둔다. "
           "(7) 제외한 후보가 있으면 answer에서 그 후보를 뺐다고 밝히고, 남은 후보 중 위치·시기가 가까운 것을 말한다. follow_ups는 결과를 좁히거나 바로잡기 위해 사용자에게 되물을 짧은 질문 0~3개(예: 큰길 쪽이었나요? 간판 색이 기억나나요?). 근거 없이 묻지 말고 후보 사이를 가르는 질문만.")
    fmt = lambda c: f"{c['id']} | tier:{'정확' if c['tier']=='exact' else '확장'} | {c['jibun']} | {c['name']} | {c['category'] or c['license_type']}{(' | AI추정업종(' + c['category_ai_basis'] + ', 확신 ' + c['category_ai_conf'] + '):' + c['category_ai']) if c.get('category_ai') else ''} | {c['start']}~{c['end']} | 층:{c['floor'] or '?'} | 등급{c['grade']} | 거리:{c['dist_m']}m | 관찰(로드뷰 간판):{(c['observed_as'] or '')[:60]}{' | 기존 수집 웹 언급:' + c['web_state'] + '(' + (c['web_n'] or '?') + '건)' if c.get('web_state') in ('strong', 'weak') else ''}"
    cl = "\n".join(fmt(c) for c in cands) or "(내부 후보 없음)"
    wl = "\n".join(f"{e['id']} | {e['title'][:80]} | {e['desc'][:160]} | {e['date']}" for e in ev) if web_used else "(웹 검색 안 함)"
    if web_used and not ev: wl = "(웹 근거 없음)"
    rj = "、".join(k.split("|")[1] for k in rejected) or "없음"
    user = f"사용자 메시지: {text}\n해석: {clue['summary']}\n사용자가 아니라고 해서 제외한 후보: {rj}\n\n[내부 후보]\n{cl}\n\n[웹 근거]\n{wl}"
    res, model, cost = liner.chat_json(sys, user, JUDGE_SCHEMA, "judge", 2000)
    ok = {c["id"] for c in cands} | {e["id"] for e in ev}
    byid = {c["id"]: c for c in cands}
    for j in res["judgements"]:
        j["evidence_ids"] = [i for i in j["evidence_ids"] if i in ok]          # 존재하지 않는 근거 제거
        c = byid.get(j["id"])
        if j["verdict"] == "확인" and not (c and c["grade"] == "A") and not any(i.startswith("W") for i in j["evidence_ids"]):
            j["verdict"] = "추정"                                                # 근거 없는 '확인'은 강등
        if c and c["tier"] == "wide" and j["verdict"] == "확인": j["verdict"] = "추정"   # 조건을 넓혀 찾은 것은 확정하지 않는다
    for l in res["leads"]: l["evidence_ids"] = [i for i in l["evidence_ids"] if i in ok]
    res["leads"] = [l for l in res["leads"] if l["evidence_ids"]]               # 근거 없는 후보는 버림
    res["follow_ups"] = res["follow_ups"][:3]
    return res, model, cost

# ---------- 후속 제안 ----------
def josa(w, with_final, without):
    """받침 유무로 조사를 고른다. 한글이 아니면 받침 없는 쪽."""
    ch = w.strip()[-1:] if w.strip() else ""
    if "가" <= ch <= "힣": return with_final if (ord(ch) - 0xAC00) % 28 else without
    return without

def make_suggestion(res, cands, clue, scope, ref=None):
    """가장 유력한 후보가 아닌 것 같을 때를 대비해, 위치를 정해 다시 찾자고 제안한다(코드가 만든다)."""
    byid = {c["id"]: c for c in cands}
    ranked = sorted((j for j in res["judgements"] if j["id"] in byid), key=lambda j: -j["confidence"])
    if not ranked: return None
    top = byid[ranked[0]["id"]]
    if scope["anchor"] is None and ref:    # 사용자가 이미 아니라고 한 후보 위치 기준
        return {"type": "radius", "anchor": ref["jibun"], "radius_m": EXPAND_RADIUS_M, "reject": None,
                "text": f"{ref['name']}{josa(ref['name'], '이', '가')} 아니라면, 그 위치(창천동 {ref['jibun']})를 기준으로 반경 {EXPAND_RADIUS_M}m 안에서 다시 찾아볼까요?"}
    if scope["anchor"] is None:        # 위치를 말하지 않았다 → 유력 후보 위치 기준 반경 50m
        return {"type": "radius", "anchor": top["jibun"], "radius_m": EXPAND_RADIUS_M, "reject": row_key(top),
                "text": f"가장 유력했던 {top['name']}{josa(top['name'], '이', '가')} 아닌 것 같다면, 그 위치(창천동 {top['jibun']})를 기준으로 반경 {EXPAND_RADIUS_M}m 안에서 다시 찾아볼까요? ({top['name']}{josa(top['name'], '은', '는')} 제외합니다)"}
    cur = scope["radius_wide"] or EXPAND_RADIUS_M
    if cur >= 300: return None
    nxt = cur + EXPAND_RADIUS_M
    return {"type": "radius", "anchor": clue["anchor"], "radius_m": nxt, "reject": None,
            "text": f"{scope['anchor']} 기준 반경을 {nxt}m로 넓혀 다시 찾아볼까요?"}

# ---------- 실행 ----------
SLIM = ("id", "tier", "jibun", "name", "category", "category_ai", "category_ai_conf", "start", "end", "floor", "grade", "score", "dist_m", "observed_as")

def run(text, state=None):
    """단계마다 dict를 yield 한다. 마지막 'done' 이벤트의 state를 화면이 보관했다가 다음 질문에 다시 보낸다."""
    state = state or {}
    total = 0.0
    yield {"step": "clue", "msg": "질문에서 정확한 정보를 추리는 중 (Liner Model)"}
    pending = state.get("pending")
    clue, m, c = parse_clue(text, state.get("clue"), pending); total += c or 0
    rejected = set() if clue["reset"] else set(state.get("rejected", []))
    nearby = False if clue["reset"] else state.get("nearby", False)
    ref = None
    last = state.get("last_top")
    if clue["reject_top"] and last and not clue["reset"]:                          # '거기가 아닌 것 같아' → 직전 1순위 후보 제외
        rejected.add(last["key"]); ref = last
    if clue["accept_suggestion"] and pending:                                      # 제안 수락: 위치와 반경을 정하고, 아니라고 한 후보는 제외
        clue["anchor"], clue["radius_m"] = pending["anchor"], pending["radius_m"]
        if pending.get("reject"): rejected.add(pending["reject"])
        nearby = True
    level = 0 if clue["reset"] else state.get("level", 0)
    level = max(0, min(MAX_LEVEL, level + {"wider": 1, "narrower": -1, "none": 0}[clue["widen"]]))
    yield {"step": "clue_done", "clue": clue, "model": m, "level": level}
    db, parcels = load_db()
    exact, wide, scope = search_tiers(db, parcels, clue, level, rejected, nearby)
    yield {"step": "cands", "msg": f"정확 검색 {len(exact)}건 · 확장 검색 {len(wide)}건", "scope": scope,
           "cands": [{k: x[k] for k in SLIM} for x in exact + wide]}
    use_web, why = web_decision(clue, exact)
    ev, queries = [], []
    if use_web:
        yield {"step": "web", "msg": f"웹 검색 사용 — {why} (Liner Search)"}
        ev, queries = gather_web(clue, exact, wide)
        yield {"step": "web_done", "msg": f"웹 근거 {len(ev)}건 수집", "evidence": ev}
    else:
        yield {"step": "web_skip", "msg": f"웹 검색 생략 — {why}"}
    cands = exact + wide
    yield {"step": "judge", "msg": "근거를 대조해 판정하는 중 (Liner Model)"}
    res, m2, c2 = judge(text, clue, cands, ev, use_web, rejected); total += c2 or 0
    sug = make_suggestion(res, cands, clue, scope, ref)
    byid = {c["id"]: c for c in cands}
    ranked = sorted((j for j in res["judgements"] if j["id"] in byid), key=lambda j: -j["confidence"])
    top = byid[ranked[0]["id"]] if ranked else None
    yield {"step": "done", "result": res, "model": m2, "cost_usd": round(total, 6), "scope": scope, "suggestion": sug,
           "web": {"used": use_web, "reason": why, "queries": queries, "n": len(ev)},
           "state": {"clue": dict(clue, widen="none", web="auto", reset=False, accept_suggestion=False), "level": level,
                     "pending": sug, "rejected": sorted(rejected), "nearby": nearby,
                     "last_top": {"key": row_key(top), "jibun": top["jibun"], "name": top["name"]} if top else None}}
