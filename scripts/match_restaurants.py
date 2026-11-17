"""창천동 일반음식점 인허가 레코드를 범위 필지(parcels.csv)에 매칭한다.

매칭 규칙
- 1차: 지번주소의 '창천동 본번-부번'이 범위 필지 지번과 일치 (match_method=jibun, 등급 A)
- 2차: 지번주소가 없거나 불일치할 때, 좌표(EPSG:2097)가 범위 필지 폴리곤 안 (match_method=coord)
  → 2026-11 확인: 이런 레코드는 주소가 4-96, 9-34 등 범위 밖 지번이었다(옛 레코드의 좌표 오류).
    그래서 확정 테이블에 넣지 않고 data/review_queue_restaurants.csv로 보낸다.
- 지번과 좌표가 서로 다른 필지를 가리키면 coord_conflict 표시

층 정보는 주소 괄호 안의 '지상N층', '지하N층', 'N층' 표기를 파싱한다(없으면 빈칸).

사용: .venv/bin/python -I scripts/match_restaurants.py
"""
import csv
import json
import re
from pathlib import Path

from pyproj import Transformer
from shapely.geometry import Point, shape

ROOT = Path(__file__).resolve().parent.parent
import sys; sys.path.insert(0, str(ROOT / "server"))
import region  # noqa: E402
# 업종별 창천동 추출본. 일반음식점 외 파일을 받으면 extract_changcheon_restaurants.py 로
# data/interim/<이름>_changcheon.csv 를 만든 뒤 아래 목록에 이름을 추가한다.
SOURCES = {"일반음식점": "restaurants", "휴게음식점": "rest_cafe", "노래연습장업": "karaoke", "미용업": "beauty",
           "관광숙박업": "tourist_hotel", "당구장업": "billiards", "목욕장업": "bath", "병원": "hospital",
           "복합유통게임제공업": "game_complex", "세탁업": "laundry", "숙박업": "lodging", "안경업": "optical",
           "약국": "pharmacy", "이용업": "barber", "인터넷컴퓨터게임시설제공업": "pc_room",
           "일반게임제공업": "game_general", "체력단련장업": "gym"}
SRCS = [(k, ROOT / f"data/interim/{v}_changcheon.csv") for k, v in SOURCES.items()
        if (ROOT / f"data/interim/{v}_changcheon.csv").exists()]
PARCELS = ROOT / "data/parcels.geojson"
OUT = ROOT / "data/business_records.csv"
REVIEW = ROOT / "data/review_queue_restaurants.csv"

to_4326 = Transformer.from_crs("EPSG:2097", "EPSG:4326", always_xy=True).transform


def date10(s):
    return (s or "").strip()[:10]


def parse_jibun(addr):
    m = re.search(re.escape(region.DONG) + r"\s+(?:산\s*)?(\d+)(?:-(\d+))?", addr or "")
    if not m:
        return None
    return f"{m.group(1)}-{m.group(2)}" if m.group(2) else m.group(1)


def parse_floor(addr):
    s = addr or ""
    m = re.search(r"지하\s*(\d+)\s*층", s)
    if m:
        return f"B{m.group(1)}"
    m = re.search(r"(?:지상\s*)?(\d+)\s*층", s)
    return m.group(1) if m else ""


def main():
    gj = json.loads(PARCELS.read_text())
    parcels = [(f["properties"], shape(f["geometry"])) for f in gj["features"]
               if f["properties"].get("role") != "road"]
    by_jibun = {p["jibun"]: p for p, _ in parcels}

    out = []
    def all_rows():
        for kind, path in SRCS:
            with path.open(encoding="utf-8-sig") as fh:
                for r in csv.DictReader(fh):
                    r["_kind"] = kind
                    yield r
    if True:
        for r in all_rows():
            jibun = parse_jibun(r["지번주소"])
            coord_parcel = None
            try:
                x, y = float(r["좌표정보(X)"]), float(r["좌표정보(Y)"])
                lon, lat = to_4326(x, y)
                pt = Point(lon, lat)
                coord_parcel = next((p for p, g in parcels if g.contains(pt)), None)
            except ValueError:
                lon = lat = None
            jp = by_jibun.get(jibun)
            if not jp and not coord_parcel:
                continue
            target = jp or coord_parcel
            out.append({
                "pnu": target["pnu"],
                "jibun": target["jibun"],
                "match_method": "jibun" if jp else "coord",
                "coord_conflict": bool(jp and coord_parcel and coord_parcel["jibun"] != jp["jibun"]),
                "name": r["사업장명"],
                "license_type": r["_kind"],
                "category": r.get("업태구분명") or r["_kind"],
                "status": r["영업상태명"],
                "licensed": date10(r["인허가일자"]),
                "closed": date10(r.get("폐업일자")),
                "floor": parse_floor(r["지번주소"] or r["도로명주소"]),
                "area_m2": r.get("소재지면적", ""),
                "jibun_addr": r["지번주소"],
                "road_addr": r["도로명주소"],
                "mgmt_no": r["관리번호"],
                "lon": round(lon, 7) if lon else "",
                "lat": round(lat, 7) if lat else "",
                "source": f"서울시 {r['_kind']} 인허가(LOCALDATA)",
                "grade": "A" if jp else "검토",
            })

    out.sort(key=lambda o: (o["jibun"], o["licensed"]))
    review = [o for o in out if o["match_method"] == "coord"]
    for path, rows in ((OUT, [o for o in out if o["match_method"] == "jibun"]), (REVIEW, review)):
        with path.open("w", encoding="utf-8-sig", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(out[0].keys()))
            w.writeheader()
            w.writerows(rows)
    out = [o for o in out if o["match_method"] == "jibun"]

    from collections import Counter
    print("records", len(out), Counter(o["match_method"] for o in out),
          "conflicts", sum(o["coord_conflict"] for o in out))
    per = Counter(o["jibun"] for o in out)
    for p, _ in sorted(parcels, key=lambda t: (t[0]["side"], t[0]["order_w2e"])):
        recs = [o for o in out if o["jibun"] == p["jibun"]]
        first = min((o["licensed"] for o in recs if o["licensed"]), default="")
        print(p["side"], p["jibun"], per.get(p["jibun"], 0), "earliest", first)


if __name__ == "__main__":
    main()
