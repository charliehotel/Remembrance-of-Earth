"""건축HUB 표제부/건축인허가 기본개요를 범위 필지별로 받아 data/raw/hub/ 에 저장한다.
사용: .venv/bin/python -I scripts/fetch_hub.py <service> <operation> <outname>
키는 .env 의 DATA_GO_KR_KEY (값은 출력하지 않는다)."""
import csv, json, sys, time, urllib.parse, urllib.request
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
key = urllib.parse.unquote([l.split("=", 1)[1].strip().strip('"') for l in open(ROOT/".env") if l.startswith("DATA_GO_KR_KEY")][0])
svc, op, name = sys.argv[1:4]
rows = list(csv.DictReader(open(ROOT/"data/parcels.csv", encoding="utf-8-sig")))
out = {}
for r in rows:
    bun, _, ji = r["jibun"].partition("-")
    items = []
    page = 1
    while True:
        q = dict(serviceKey=key, sigunguCd="11410", bjdongCd="11600", platGbCd="0", bun=bun.zfill(4), ji=(ji or "0").zfill(4), _type="json", numOfRows=100, pageNo=page)
        u = f"https://apis.data.go.kr/1613000/{svc}/{op}?" + urllib.parse.urlencode(q)
        for t in range(4):
            try:
                d = json.loads(urllib.request.urlopen(u, timeout=40).read()); break
            except Exception as e:
                d = None; time.sleep(2)
        if d is None: print("FAIL", r["jibun"]); break
        b = d["response"]["body"]; it = b["items"]
        it = it["item"] if it else []
        items += it if isinstance(it, list) else [it]
        if page * 100 >= int(b.get("totalCount", 0)): break
        page += 1
    out[r["jibun"]] = items
    print(r["jibun"], len(items))
(ROOT/f"data/raw/hub/{name}.json").write_text(json.dumps(out, ensure_ascii=False))
