"""창천교회 반경 150m 안의 비도로 필지를 골라 data/parcels_r150.csv 를 만든다.
기존 파이프라인이 읽는 data/parcels.csv(연세로12길 25필지)는 건드리지 않는다.
in_core 열은 그 25필지에 속하면 True. 확장 단계에서는 in_core=False 인 필지만 새로 처리한다.

사용: .venv/bin/python -I scripts/build_parcels_r150.py
"""
import csv
import json
import math
import re
from pathlib import Path

from shapely.geometry import shape

ROOT = Path(__file__).resolve().parent.parent
import sys; sys.path.insert(0, str(ROOT / "server"))
import region  # noqa: E402
SRC = ROOT / "data/raw/vworld/cadastral_bbox.json"
CORE = ROOT / "data/parcels.csv"
OUT = ROOT / "data/parcels_r150.csv"
CENTER = tuple(region.R["center"])  # scene.json context.center (창천교회 일대)
RADIUS_M = 150


def dist_m(x, y):
    return math.hypot((x - CENTER[0]) * 88000, (y - CENTER[1]) * 111000)


def main():
    core = {r["jibun"] for r in csv.DictReader(CORE.open(encoding="utf-8-sig"))}
    feats = json.loads(SRC.read_text())["response"]["result"]["featureCollection"]["features"]
    rows = []
    for f in feats:
        p = f["properties"]
        m = re.match(r"(\S+?)\s*(\D+)$", p["jibun"])
        no, jimok = m.group(1), m.group(2).strip()
        if jimok == "도":
            continue
        c = shape(f["geometry"]).centroid
        d = dist_m(c.x, c.y)
        if d > RADIUS_M:
            continue
        rows.append({"pnu": p["pnu"], "jibun": no, "jimok": jimok, "addr": p["addr"],
                     "lon": round(c.x, 7), "lat": round(c.y, 7), "dist_m": round(d, 1),
                     "in_core": no in core})
    rows.sort(key=lambda r: r["dist_m"])
    with OUT.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    new = [r for r in rows if not r["in_core"]]
    print(f"r150 비도로 필지={len(rows)} (기존 25 중 {len(rows)-len(new)}) 신규={len(new)}")
    miss = core - {r["jibun"] for r in rows}
    print("기존 필지 중 150m 밖:", sorted(miss))


if __name__ == "__main__":
    main()
