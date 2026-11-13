"""로드뷰 관찰(observations.csv)의 상호를 인허가 기록(business_records.csv)과 필지 단위로 대조한다.
관찰 상호의 핵심어(괄호·주석 제거)가 같은 필지 인허가 사업장명에 들어 있으면 matched.
없으면 data/review_queue_observations.csv 로 보낸다(인허가 누락·상호 변경·판독 오류 후보).
사용: .venv/bin/python -I scripts/crosscheck.py"""
import csv, re
from collections import defaultdict
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
norm = lambda s: re.sub(r"[^가-힣A-Za-z0-9]", "", s).lower()
NOISE = re.compile(r"미확인|확인|표기|관계|출입구|점포|간판|안내|이용|구획|공사|관찰|불명|잔존|기존|옛|시설|배치|변화|임대|좌측|우측|중앙|층|판매|철거|흔적|영업|적법|독립|계단|공용")
# 영문·한글 표기 별칭(관찰 상호 -> 인허가명에 포함될 문자열). 같은 가게의 다른 표기만 넣는다.
ALIAS = {"chicky2": "치키바이투", "chickybytwo": "치키바이투", "travellounge": "트래블라운지", "cafefruity": "프루티", "whitenoraebang": "화이트", "white노래방": "화이트", "white노래연습장": "화이트", "와이트노래방": "화이트", "vistabeautyhair": "비스타뷰티헤어", "cafdirect": "카페다이렉트",
         "caffecaffe": "카페카페", "fromhearts": "프롬하츠", "papaya": "파파야", "2inonediner": "투인원",
         "elsalud": "엘살루드", "cafeau": "에이유", "아담앤이브waxingtanning": "아담앤이브",
         "premiumrestaurantpubobject": "오브젝트", "자가제면풍년": "풍년", "yeti예티": "예티", "맥주창고": "비어비워",  # 46-2 비어비워신촌2호점(2012-10~2016-05), 체인명 "비어비워 신촌맥주창고"
         "우촌갈비": "우촌",
         "barceo": "씨이오", "ceo": "씨이오", "mjhair": "엠제이", "newtown": "뉴타운", "nextedition": "넥스트"}
# 한 건물이 여러 지번에 걸친 경우 인허가가 다른 지번으로 나 있다(2-27 간판 = 2-17 인허가: 우촌·오브젝트·풍년).
PARCEL_GROUP = {"2-27": ["2-17"], "2-17": ["2-27"]}
def licenses_for(jibun, lic):
    return lic[jibun] + [b for j in PARCEL_GROUP.get(jibun, []) for b in lic[j]]
def names(raw):
    s = re.sub(r"\([^)]*\)", " ", raw)
    out = []
    for x in re.split(r"[·/,]", s):
        n = norm(x)
        if len(n) >= 2 and not NOISE.search(x):
            out.append(ALIAS.get(n, n))
    return out
def match(n, recs):
    """관찰 핵심어 n과 같은 가게로 보이는 인허가 레코드 목록."""
    return [b for b in recs if n in norm(b["name"]) or norm(b["name"]) in n and len(norm(b["name"])) >= 3]
def main():
    obs = list(csv.DictReader(open(ROOT/"data/observations.csv", encoding="utf-8-sig")))
    bus = list(csv.DictReader(open(ROOT/"data/business_records.csv", encoding="utf-8-sig")))
    lic = defaultdict(list)
    for b in bus: lic[b["jibun"]].append(b)
    res, seen = [], set()
    for o in obs:
        if o["status"] not in ("named", "tentative", "partial"): continue
        for n in names(o["raw"]):
            key = (o["jibun"], n)
            hit = match(n, licenses_for(o["jibun"], lic))
            res.append({"jibun": o["jibun"], "unit": o["unit"], "date": o["date"], "observed": o["raw"], "key": n,
                        "matched": bool(hit), "license_name": hit[0]["name"] if hit else "",
                        "licensed": hit[0]["licensed"] if hit else "", "closed": hit[0]["closed"] if hit else ""})
    uniq = {}
    for r in res:
        k = (r["jibun"], r["key"])
        if k not in uniq or (r["matched"] and not uniq[k]["matched"]): uniq[k] = r
    rows = list(uniq.values())
    m = [r for r in rows if r["matched"]]; u = [r for r in rows if not r["matched"]]
    with open(ROOT/"data/review_queue_observations.csv", "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(sorted(u, key=lambda r: (r["jibun"], r["date"])))
    print("distinct names", len(rows), "matched", len(m), "unmatched", len(u))
    from collections import Counter
    print(Counter(r["jibun"] for r in u).most_common())
    for r in sorted(m, key=lambda r: r["date"])[:0]: pass
if __name__ == "__main__":
    main()
