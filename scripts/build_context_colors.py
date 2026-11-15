"""주변 건물(회색 맥락 건물)의 지붕색·벽색을 만든다: data/context_colors.json

- 지붕색: data/raw/satellite/위성사진_창천교회 일대_원본.png(정사 위성사진)를 건물 외곽선 안쪽에서 표본 추출한다.
  사진과 지도 좌표는 창천교회 지붕(41m x 25m)을 기준으로 맞췄다(7.0px/m, 교회 원점이 (431,141)px). 외곽선과 지붕이 몇 px 어긋나도
  견디도록 외곽선을 1.2m 안쪽으로 줄이고, 그림자(어두운 픽셀)는 빼고 중앙값을 쓴다.
- 벽색: 3D 사진(3D사진_창천교회 일대_상호 표시.png)을 scripts/calibrate_3d_cam.py 가 만든 카메라(data/context_cam3d.json)로
  건물 위에 투영해, 카메라를 향한 벽면 중앙부(폭 15~85%, 높이 20~85%)의 화소를 먼 건물부터 그려 가림을 반영한 뒤 건물별 중앙값을 쓴다.
  사진에 안 잡히거나 표본이 적은 건물(약 40화소 미만)은 3D 사진에서 읽은 팔레트(흰색·회백색·베이지·벽돌·황갈색·청회색·진회색)를
  높이에 따라 골라 채운다(ws=0). 사진에서 뽑은 것은 ws=1. 팔레트의 WALL_OVERRIDE 는 표본이 없을 때만 쓴다.
- 키: 대표점(m, 소수 1자리)+면적. export_web.py 가 같은 방식으로 키를 만들어 합친다.
사용: .venv/bin/python -I scripts/build_context_colors.py   (Pillow 필요)
"""
import json
import math
import colorsys
from pathlib import Path

from PIL import Image
from shapely.geometry import shape, Polygon

ROOT = Path(__file__).resolve().parent.parent
SAT = ROOT / "data/raw/satellite/위성사진_창천교회 일대_원본.png"
OUT = ROOT / "data/context_colors.json"
KX, KY = 111320 * math.cos(math.radians(37.559)), 110540
PX_PER_M, OX, OY = 7.0, 431.0, 141.0   # 위성사진 보정값(교회 원점의 화소 위치)

# 3D 사진 벽면에서 읽은 색
PALETTE = {
    "white":  "#e9e6df",   # 흰색 마감(금송빌딩 등 고층)
    "gray":   "#cdcbc6",   # 회백색 콘크리트·드라이비트
    "beige":  "#d9c8a9",   # 베이지 타일·스터코
    "brick":  "#b3735c",   # 붉은 벽돌
    "tan":    "#a98f72",   # 황갈색 벽돌
    "slate":  "#aeb8c2",   # 청회색 유리·패널
    "dark":   "#8c8b8e",   # 진회색(검은 유리·노후 시멘트)
}
# 건물 인덱스 → 팔레트 이름(3D 사진에서 직접 확인한 것)
WALL_OVERRIDE = {
    4: "white",    # 금송빌딩(높이 33.5m, 흰색 고층)
    3: "white",    # 삼각형 흰색 건물(진영빌딩·탐앤탐스 쪽)
}


def load_cal():
    import importlib.util
    spec = importlib.util.spec_from_file_location("cal3d", ROOT / "scripts/calibrate_3d_cam.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def wall_samples():
    """건물 인덱스 → (벽 색 RGB, 화소 수). 카메라 파일이 없으면 빈 dict."""
    import numpy as np
    camf = ROOT / "data/context_cam3d.json"
    if not camf.exists():
        return {}
    cal = load_cal()
    p = np.array(json.loads(camf.read_text())["params"])
    photo = Image.open(cal.PHOTO).convert("RGB")
    W, H = photo.size
    arr = np.asarray(photo).astype(float)
    blds = cal.load_buildings()
    lab = cal.label_image(p, blds, W, H, walls=True)
    out = {}
    for i in range(len(blds)):
        m = lab == 2 * i + 2
        n = int(m.sum())
        if n < 40:
            continue
        a = arr[m]
        lum = a @ np.array([0.299, 0.587, 0.114])
        a, lum = a[lum > 45], lum[lum > 45]       # 그림자 속·검은 간판 제외
        if len(a) < 30:
            continue
        lo, hi = np.percentile(lum, [60, 95])      # 사진에 구워진 그림자를 피해 햇빛 받은 쪽 위주
        sel = (lum >= lo) & (lum <= hi)
        c = np.median(a[sel], axis=0)
        out[i] = (255 * (c / 255) ** 0.75, n)   # 사진 전체에 깔린 그림자(어둡게 구워진 면)를 보정하는 감마 0.75
    return out


def key_of(g):
    rp = g.representative_point()
    return f"{rp.x:.1f},{rp.y:.1f},{round(g.area)}"


def hexc(rgb):
    return "#%02x%02x%02x" % tuple(int(round(v)) for v in rgb)


def roof_color(img, poly_px, w, h):
    """다각형(화소 좌표) 안의 지붕색(중앙값, 그림자 제외). 표본이 부족하면 None."""
    ins = poly_px.buffer(-1.2 * PX_PER_M)
    if ins.is_empty or ins.area < 25:
        ins = poly_px.buffer(-0.5 * PX_PER_M)
    if ins.is_empty:
        return None, 0
    x0, y0, x1, y1 = [int(v) for v in ins.bounds]
    if x1 < 0 or y1 < 0 or x0 >= w or y0 >= h:
        return None, 0
    from shapely import contains_xy
    import numpy as np
    xs = np.arange(max(x0, 0), min(x1 + 1, w))
    ys = np.arange(max(y0, 0), min(y1 + 1, h))
    if len(xs) == 0 or len(ys) == 0:
        return None, 0
    gx, gy = np.meshgrid(xs, ys)
    m = contains_xy(ins, gx + 0.5, gy + 0.5)
    if m.sum() < 8:
        return None, 0
    a = np.asarray(img)[gy[m], gx[m], :3].astype(float)
    lum = a @ np.array([0.299, 0.587, 0.114])
    # 그림자·짙은 수목 제외(너무 어두운 것), 단 전부 어두운 지붕이면 그대로 쓴다
    keep = lum > 62
    if keep.sum() >= max(8, 0.25 * len(a)):
        a, lum = a[keep], lum[keep]
    # 햇빛 받은 면을 대표색으로: 밝기 55~80 백분위 구간 화소의 중앙값(그림자·수목 그늘이 섞인 중앙값보다 지붕색에 가깝다)
    lo, hi = np.percentile(lum, [55, 80])
    sel = (lum >= lo) & (lum <= hi)
    return np.median(a[sel] if sel.sum() >= 4 else a, axis=0), int(m.sum())


def classify_wall(i, height, roof_rgb, rng_val):
    if i in WALL_OVERRIDE:
        return PALETTE[WALL_OVERRIDE[i]]
    # 가중치: 저층일수록 벽돌·베이지, 고층일수록 흰색·회백·청회
    if height >= 18:
        opts = [("white", 3), ("gray", 3), ("slate", 3), ("beige", 1), ("dark", 1)]
    elif height >= 11:
        opts = [("gray", 3), ("white", 2), ("beige", 2), ("brick", 2), ("slate", 1), ("tan", 1)]
    else:
        opts = [("brick", 3), ("beige", 3), ("gray", 2), ("tan", 2), ("white", 1), ("dark", 1)]
    tot = sum(w for _, w in opts)
    r = rng_val * tot
    for name, w in opts:
        r -= w
        if r <= 0:
            return PALETTE[name]
    return PALETTE[opts[-1][0]]


def main():
    sc = json.loads((ROOT / "web/scene.json").read_text())
    o = sc["context"]["center"]
    to_m = lambda lon, lat: ((lon - o[0]) * KX, (lat - o[1]) * KY)
    img = Image.open(SAT).convert("RGB")
    W, H = img.size
    import numpy as np
    out = {}
    walls = wall_samples()
    print("wall samples from 3D photo:", len(walls))
    for i, f in enumerate(sc["context"]["buildings"]["features"]):
        ring = [to_m(*p) for p in f["geometry"]["coordinates"][0]]
        g = Polygon(ring).buffer(0)
        if g.is_empty:
            continue
        height = f["properties"]["height"]
        poly_px = Polygon([(OX + x * PX_PER_M, OY - y * PX_PER_M) for x, y in ring]).buffer(0)
        rgb, n = roof_color(img, poly_px, W, H)
        rng_val = ((i * 2654435761) % 1000) / 1000.0
        if i in walls:
            wall, ws = hexc(walls[i][0]), 1
        else:
            wall, ws = classify_wall(i, height, rgb, rng_val), 0
        ent = {"wc": wall, "ws": ws}
        if rgb is not None:
            # 위성사진은 채도가 낮고 밝아 보여서 살짝 보정(채도 +12%)
            h_, s_, v_ = colorsys.rgb_to_hsv(*(c / 255 for c in rgb))
            r, gg, b = colorsys.hsv_to_rgb(h_, min(1, s_ * 1.12), v_)
            ent["rc"] = hexc((r * 255, gg * 255, b * 255))
            ent["n"] = n
        out[key_of(g)] = ent
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=0))
    have = sum(1 for v in out.values() if "rc" in v)
    print("buildings", len(out), "with roof color", have, "->", OUT.relative_to(ROOT))


if __name__ == "__main__":
    main()
