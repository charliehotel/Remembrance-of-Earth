"""연속지적도 응답에서 연세로12길(창천교회 47-2 ~ 아웃백 2-6) 범위 필지를 골라
data/parcels.geojson, data/parcels.csv 를 만든다.

방법
1. 지목이 '도'(도로)인 필지 중 교회~아웃백 사이 길을 이루는 필지를 씨앗에서 확장해 찾는다.
2. 도로 필지와 맞닿은 비도로 필지 중 경도가 범위 안인 것을 '길에 면한 필지'로 고른다.
3. 로드뷰 CSV 조사 지번은 길에 면하지 않아도 포함한다(예: 2-27).
4. 길 중심선 대비 남/북 구분, 서→동 순서, 면적(EPSG:5186), 조사 여부, 앵커를 기록한다.

사용: .venv/bin/python -I scripts/build_parcels.py
"""
import csv
import json
import re
from pathlib import Path

from pyproj import Transformer
from shapely.geometry import mapping, shape
import numpy as np
import shapely
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data/raw/vworld/cadastral_bbox.json"
OUT_GEOJSON = ROOT / "data/parcels.geojson"
OUT_CSV = ROOT / "data/parcels.csv"

ROAD_SEEDS = {"2-16", "2-89", "46-1", "47-28"}  # 교회~아웃백 사이 연세로12길 도로 필지
ROAD_WINDOW = (126.9373, 126.9392, 37.5588, 37.5593)  # 도로 확장 허용 범위(lon, lon, lat, lat)
RANGE_LON = (126.9375, 126.9390)  # 교회 서측 경계 ~ 아웃백 동측 경계
SURVEYED = {"47-12", "46-12", "46-2", "2-27", "2-19", "2-21", "2-22", "2-23",
            "2-14", "2-2", "2-7", "2-6"}
ANCHORS = {"47-2": "창천감리교회", "2-6": "아웃백 스테이크하우스"}
SLIVER_M2 = 20

to_5186 = Transformer.from_crs("EPSG:4326", "EPSG:5186", always_xy=True).transform


def main():
    data = json.loads(SRC.read_text())
    feats = data["response"]["result"]["featureCollection"]["features"]
    parcels = {}
    for f in feats:
        p = f["properties"]
        m = re.match(r"(\S+?)\s*(\D+)$", p["jibun"])
        parcels[p["pnu"]] = {"no": m.group(1), "jimok": m.group(2).strip(),
                             "geom": shape(f["geometry"]), "props": p}

    roads = {k for k, v in parcels.items() if v["jimok"] == "도" and v["no"] in ROAD_SEEDS}
    x0, x1, y0, y1 = ROAD_WINDOW
    for _ in range(5):
        u = unary_union([parcels[k]["geom"] for k in roads]).buffer(1e-6)
        grown = {k for k, v in parcels.items()
                 if v["jimok"] == "도" and k not in roads and v["geom"].intersects(u)
                 and x0 < v["geom"].centroid.x < x1 and y0 < v["geom"].centroid.y < y1}
        if not grown:
            break
        roads |= grown
    road_union = unary_union([parcels[k]["geom"] for k in roads])
    road_touch = road_union.buffer(2e-6)
    mid_lat = road_union.centroid.y

    selected = []
    for k, v in parcels.items():
        if k in roads or v["jimok"] == "도":
            continue
        cx = v["geom"].centroid.x
        facing = v["geom"].intersects(road_touch) and RANGE_LON[0] <= cx <= RANGE_LON[1]
        if facing or v["no"] in SURVEYED:
            selected.append((k, v, facing))

    rows, features = [], []
    for side in ("N", "S"):
        group = [s for s in selected if (s[1]["geom"].centroid.y > mid_lat) == (side == "N")]
        for order, (k, v, facing) in enumerate(sorted(group, key=lambda s: s[1]["geom"].centroid.x), 1):
            area = round(shapely.transform(v["geom"], lambda c: np.column_stack(to_5186(c[:, 0], c[:, 1]))).area, 1)
            c = v["geom"].centroid
            row = {
                "pnu": k, "jibun": v["no"], "jimok": v["jimok"], "addr": v["props"]["addr"],
                "side": side, "order_w2e": order, "area_m2": area,
                "street_facing": facing, "surveyed_roadview": v["no"] in SURVEYED,
                "anchor": ANCHORS.get(v["no"], ""), "sliver": area < SLIVER_M2,
                "lon": round(c.x, 7), "lat": round(c.y, 7),
                "gosi_year": v["props"].get("gosi_year"), "jiga": v["props"].get("jiga"),
            }
            rows.append(row)
            features.append({"type": "Feature", "properties": row, "geometry": mapping(v["geom"])})

    road_features = [{"type": "Feature",
                      "properties": {"pnu": k, "jibun": parcels[k]["no"], "jimok": "도", "role": "road"},
                      "geometry": mapping(parcels[k]["geom"])} for k in sorted(roads)]

    OUT_GEOJSON.write_text(json.dumps({
        "type": "FeatureCollection",
        "name": "yeonsero12gil_parcels",
        "crs_note": "EPSG:4326 (lon, lat)",
        "source": "V-World 연속지적도 LP_PA_CBND_BUBUN",
        "features": features + road_features,
    }, ensure_ascii=False))
    with OUT_CSV.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    missing = SURVEYED - {r["jibun"] for r in rows}
    print(f"parcels={len(rows)} roads={len(roads)} missing_surveyed={sorted(missing)}")
    for r in rows:
        flags = [f for f, on in (("조사", r["surveyed_roadview"]), ("면함", r["street_facing"]),
                                 ("소필지", r["sliver"])) if on]
        print(r["side"], r["order_w2e"], r["jibun"], r["jimok"], r["area_m2"], r["anchor"], ",".join(flags))


if __name__ == "__main__":
    main()
