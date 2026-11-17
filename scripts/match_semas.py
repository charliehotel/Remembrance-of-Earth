"""상가(상권)정보 분기 스냅샷(data/semas/changcheon_*.csv, scripts/extract_semas.py 가 만든다)과 우리 업소를 연결한다.

스냅샷에 상호가 있으면 '그 시점에 영업 중'이라는 관측이다(로드뷰 간판 관측과 같은 성격이고, 가로수에 가려지지도 않는다).
업소마다 관측된 첫·마지막 스냅샷 날짜를 data/semas_match.csv 로 쓰고, server/agent.py load_db() 가 읽어 행에 붙인다.
규칙
  · 같은 필지 안에서 상호를 정규화해 포함 관계이거나 유사도 0.85 이상일 때만 같은 업소로 본다. 스냅샷마다 한 업소는 한 번만 쓴다.
  · 같은 상호의 후속 업소와 섞이지 않도록 관측 창을 둔다: 개업 기록 1년 전부터 폐업 기록 1년 뒤까지(영업 중이면 현재까지)의 스냅샷만 센다.
  · 층정보는 가장 최근 관측의 값을 남긴다.
사용: python3 scripts/match_semas.py
"""
import csv, re, sys, difflib, collections
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "server"))
import agent, analysis
ROOT = Path(__file__).resolve().parent.parent
snaps = {}
for p in sorted((ROOT / "data/semas").glob("changcheon_*.csv")):
    snaps[p.stem.split("_")[1]] = list(csv.DictReader(open(p, encoding="utf-8-sig")))
if not snaps: sys.exit("data/semas/changcheon_*.csv 가 없습니다. 먼저 scripts/extract_semas.py 를 실행하세요.")
norm = lambda s: re.sub(r"[\s\(\)\[\]·\-_.,]|점$|본점|신촌|연세|창천|\(주\)|\(유\)|주식회사|유한회사", "", s.lower())
tf = lambda d: analysis._t(f"{d[:4]}-{d[4:6]}-{d[6:]}")
byp = {d: collections.defaultdict(list) for d in snaps}
for d, rs in snaps.items():
    for r in rs: byp[d][r["jibun"]].append(r)
db, parcels = agent.load_db()
cand = sorted((r for r in db if r["source"] != "로드뷰 직접 조사"), key=lambda r: (r["jibun"], r["start"]))
used = {d: set() for d in snaps}
out = []
for r in cand:
    s = analysis._t(r["start"]); e = analysis._t(r["end"]) if r["end"] else analysis.T_NOW + 1
    seen = []
    for d in sorted(snaps):
        if not (s - 1 <= tf(d) <= e + 1): continue
        best = (0.0, None)
        for x in byp[d].get(r["jibun"], []):
            if x["id"] in used[d]: continue
            a, c = norm(r["name"]), norm(x["name"])
            sc = difflib.SequenceMatcher(None, a, c).ratio()
            if a and c and (a in c or c in a): sc = max(sc, 0.95)
            if sc > best[0]: best = (sc, x)
        if best[1] and best[0] >= 0.85:
            used[d].add(best[1]["id"]); seen.append((d, best[1], best[0]))
    if seen:
        last = seen[-1][1]
        out.append({"key": agent.row_key(r), "first_seen": f"{seen[0][0][:4]}-{seen[0][0][4:6]}-{seen[0][0][6:]}", "last_seen": f"{seen[-1][0][:4]}-{seen[-1][0][4:6]}-{seen[-1][0][6:]}",
                    "n_seen": len(seen), "semas_id": last["id"], "semas_name": last["name"], "floor": last["floor"], "score_min": round(min(x[2] for x in seen), 2)})
with open(ROOT / "data/semas_match.csv", "w", encoding="utf-8-sig", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(out[0])); w.writeheader(); w.writerows(out)
latest = max(snaps)
openr = [r for r in cand if not r["end"]]; closed = [r for r in cand if r["end"]]
keys = {o["key"]: o for o in out}
print(f"스냅샷 {len(snaps)}개({min(snaps)}~{latest}), 창천동 업소 수 " + ", ".join(f"{d[:6]}:{len(rs)}" for d, rs in list(snaps.items())[:6]) + (" …" if len(snaps) > 6 else ""))
print(f"연결된 우리 업소 {len(out)}건 / 전체 {len(cand)}건. 영업 중 기록 {len(openr)}건 중 {sum(1 for r in openr if agent.row_key(r) in keys)}건, 폐업 기록 {len(closed)}건 중 {sum(1 for r in closed if agent.row_key(r) in keys)}건")
nl = [o for o in out if o["last_seen"].replace("-", "") < latest]
print(f"폐업 시점 하한이 새로 생기는 업소(마지막 관측이 최신 스냅샷 이전) {len(nl)}건, 평균 관측 {sum(o['n_seen'] for o in out) / len(out):.1f}개 스냅샷")
lo = [o for o in out if o["score_min"] < 0.95]
print(f"상호 표기가 달라 유사도 0.85~0.95로 연결된 {len(lo)}건 예: " + ", ".join(f"{o['key'].split('|')[1]}↔{o['semas_name']}" for o in lo[:6]))
