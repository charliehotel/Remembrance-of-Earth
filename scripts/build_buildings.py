"""V-World GIS건물통합정보(LT_C_BLDGINFO)를 필지(parcels.geojson)와 공간 결합해
data/buildings_current.geojson, data/buildings_current.csv 를 만든다.
건물은 면적이 가장 많이 겹치는 필지에 배정하고, 여러 필지에 걸치면 spans 에 기록한다.
사용: .venv/bin/python -I scripts/build_buildings.py
"""
import csv, json
from pathlib import Path
from shapely.geometry import shape, mapping
import numpy as np, shapely
from pyproj import Transformer

ROOT = Path(__file__).resolve().parent.parent
t = Transformer.from_crs("EPSG:4326", "EPSG:5186", always_xy=True).transform
def m2(g): return shapely.transform(g, lambda c: np.column_stack(t(c[:,0], c[:,1]))).area

par = [(f["properties"], shape(f["geometry"])) for f in json.loads((ROOT/"data/parcels.geojson").read_text())["features"] if f["properties"].get("role") != "road"]
fs = json.loads((ROOT/"data/raw/vworld/LT_C_BLDGINFO_bbox.json").read_text())["response"]["result"]["featureCollection"]["features"]

feats, rows = [], []
for i, f in enumerate(fs):
    g = shape(f["geometry"]).buffer(0); p = f["properties"]
    ov = sorted(((m2(g.intersection(pg)), pp["jibun"], pp["pnu"]) for pp, pg in par if g.intersects(pg)), reverse=True)
    ov = [o for o in ov if o[0] > 0.5]
    if not ov: continue
    tot = m2(g)
    best = ov[0]
    row = {"bid": f"B{i:03d}", "pnu": best[2], "jibun": best[1], "footprint_m2": round(tot,1),
           "share_in_main": round(best[0]/tot,2), "spans": ";".join(o[1] for o in ov),
           "height_m": p["height"], "floors_up": p["grnd_flr"], "floors_down": p["ugrnd_flr"],
           "approved": p["useapr_day"], "structure": p["strct_cd"], "usability": p["usability"],
           "name": p["bld_nm"], "archarea": p["archarea"], "totalarea": p["totalarea"], "platarea": p["platarea"]}
    rows.append(row); feats.append({"type":"Feature","properties":row,"geometry":mapping(g)})
(ROOT/"data/buildings_current.geojson").write_text(json.dumps({"type":"FeatureCollection","features":feats}, ensure_ascii=False))
rows.sort(key=lambda r:(r["jibun"], r["bid"]))
with (ROOT/"data/buildings_current.csv").open("w", encoding="utf-8-sig", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
have = {r["jibun"] for r in rows}
print("buildings", len(rows), "parcels_without_building", [p["jibun"] for p,_ in par if p["jibun"] not in have])
for r in rows: print(r["jibun"], r["bid"], r["footprint_m2"], "h", r["height_m"], "F", r["floors_up"], "B", r["floors_down"], r["approved"], "span", r["spans"], r["share_in_main"])
