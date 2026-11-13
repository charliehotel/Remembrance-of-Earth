"""창천교회(47-2 지오코딩 점) 반경 150m를 덮는 박스로 V-World GIS건물통합정보(LT_C_BLDGINFO)를 받아
data/raw/vworld/LT_C_BLDGINFO_r100.json 에 저장한다. export_web.py 가 이 파일을 읽어 주변 회색 건물로 쓴다.
박스는 반경 + 여유(MARGIN_M)로 잡아 경계에 걸친 건물도 받는다. 원 안 판정은 export_web.py 가 대표점으로 한다.
사용: .venv/bin/python -I scripts/fetch_bldg_r100.py
"""
import http.client, json, os, time, urllib.error, urllib.parse, urllib.request
from pathlib import Path
from pyproj import Transformer

ROOT = Path(__file__).resolve().parent.parent
RADIUS_M, MARGIN_M = 150, 30
OUT = ROOT / "data/raw/vworld/LT_C_BLDGINFO_r100.json"


def env(k):
    for line in (ROOT / ".env").read_text().splitlines():
        if line.startswith(k + "="):
            return line.split("=", 1)[1].strip().strip('"\'')
    return os.environ.get(k)


def get(url, tries=4):
    for i in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=30) as resp:
                return json.loads(resp.read())
        except (http.client.IncompleteRead, urllib.error.URLError, TimeoutError):
            if i == tries - 1:
                raise
            time.sleep(1.5 * (i + 1))


def main():
    gc = json.loads((ROOT / "data/raw/vworld/geocode_church.json").read_text())["response"]["result"]["items"][0]["point"]
    fwd = Transformer.from_crs("EPSG:4326", "EPSG:5186", always_xy=True)
    inv = Transformer.from_crs("EPSG:5186", "EPSG:4326", always_xy=True)
    x, y = fwd.transform(float(gc["x"]), float(gc["y"]))
    r = RADIUS_M + MARGIN_M
    x0, y0 = inv.transform(x - r, y - r)
    x1, y1 = inv.transform(x + r, y + r)
    feats, page = [], 1
    while True:
        q = {"service": "data", "request": "GetFeature", "data": "LT_C_BLDGINFO", "key": env("VWORLD_KEY"),
             "domain": env("VWORLD_DOMAIN") or "localhost", "format": "json", "size": "100", "page": str(page),
             "geometry": "true", "attribute": "true", "crs": "EPSG:4326",
             "geomFilter": f"BOX({x0},{y0},{x1},{y1})"}
        d = get("https://api.vworld.kr/req/data?" + urllib.parse.urlencode(q))
        st = d["response"]["status"]
        if st == "NOT_FOUND":
            break
        if st != "OK":
            raise SystemExit(f"V-World 오류: {json.dumps(d['response'], ensure_ascii=False)[:500]}")
        feats += d["response"]["result"]["featureCollection"]["features"]
        if page >= int(d["response"]["page"]["total"]):
            break
        page += 1
    d["response"]["result"]["featureCollection"]["features"] = feats
    d["response"]["result"]["featureCollection"]["bbox"] = [x0, y0, x1, y1]
    d["response"]["record"] = {"total": str(len(feats)), "current": str(len(feats))}
    OUT.write_text(json.dumps(d, ensure_ascii=False))
    print(f"{len(feats)}동 → {OUT.relative_to(ROOT)}  BOX({x0:.6f},{y0:.6f},{x1:.6f},{y1:.6f})")


if __name__ == "__main__":
    main()
