"""창천교회 북쪽 경의중앙선 철도 둑을 만든다: data/rail.geojson (export_web.py 가 scene.json 의 rail 로 합친다)

근거
- 철도 용지: V-World 연속지적도에서 지목이 '철'인 필지의 합집합이 둑 바닥 면적이다(교회 필지 바로 북쪽, 폭 약 50~80m).
- 선로대: 둑 중심선(y = 47 + 0.04 x, 교회 필지 중심 기준 미터)에서 ±11m. 위성사진상 선로 4~5줄.
- 연세로 굴다리: 연세로가 둑을 가로지르는 곳(x -64~-46). 지적도에서 철도 용지가 도로를 덮고 있어 틈이 안 보이므로 직접 뚫는다.
- 신촌 토끼굴: 위치 미확인이라 아직 없음.
- 높이: 선로면 10.5m(로드뷰에서 건물 3~4층 높이로 확인), 굴다리 통로 5.2m, 지하보도 입구 3.0m. 비탈은 약 50° 경사를 15층 계단으로 근사. 둑 아래 끝은 y=21(건물 북쪽 벽에서 6m 뒤, 뒷골목).
- 둑 동쪽은 신촌역 구내라 x>100 에서는 선로대 주변 20m 만 만든다(역사·승강장은 아직 구현하지 않음).

출력 속성: b(바닥 m), h(꼭대기 m), c(색), k(종류)
사용: .venv/bin/python -I scripts/build_rail.py
"""
import json
import math
import re
from pathlib import Path

from shapely.affinity import affine_transform
from shapely.geometry import LineString, Polygon, box, mapping, shape
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data/raw/vworld/cadastral_bbox.json"
OUT = ROOT / "data/rail.geojson"
C = (126.93756304043873, 37.55915909082795)        # 교회 필지 중심(지역 좌표 원점)
KX, KY = 111320 * math.cos(math.radians(37.559)), 110540

DECK_H = 10.5                                   # 선로면 높이(로드뷰: 건물 3~4층 높이)
CLEAR_ROAD = 5.2
# 비탈: MapLibre 는 경사면을 못 그려서, 가장자리에서 0.6m 씩 안쪽으로 줄인 면을 0.72m 씩 높여 쌓는다(경사 약 50°, 15층, 밑변 약 9m).
# 로드뷰에서 북쪽(성산로 쪽) 둑은 길가에 거의 붙은 가파른 옹벽이라 완만하게(35°) 그리면 도로 쪽으로 너무 퍼진다.
SLOPE_K, STEP_E = 1.2, 0.6
HALF_W = 25.0          # 둑 반폭(중심선 기준)
FOOT_Y = 21.0          # 둑 아래(남쪽) 끝. 교회·약국 건물 북쪽 벽(y≈15)에서 약 6m 뒤: 그 사이가 뒷골목(지도에 연세로 골목으로 표시)
WALL_COL, GREEN_COL = "#d9d6cf", "#88a070"
COL = {"slope": "#7f9669", "deck": "#bdbab3", "lintel": "#a9a69f", "floor": "#cfcdc8", "rail": "#5b5751"}


def center_y(x):
    return 47 + 0.04 * x


def to_local(g):
    return affine_transform(g, [KX, 0, 0, KY, -C[0] * KX, -C[1] * KY])


def to_ll(g):
    return affine_transform(g, [1 / KX, 0, 0, 1 / KY, C[0], C[1]])


def main():
    feats = json.loads(SRC.read_text())["response"]["result"]["featureCollection"]["features"]
    rail, paths = [], {}
    for f in feats:
        p = f["properties"]
        m = re.match(r"(\S+?)\s*(\D+)$", p["jibun"])
        jimok = m.group(2).strip()
        g = to_local(shape(f["geometry"]))
        if jimok == "철":
            rail.append(g)
        elif jimok == "도":
            paths[m.group(1)] = g

    # 철도 용지 사이에 낀 좁은 도로·보행로 필지(지하보도 82-15, 82-17 등)는 둑 밑을 지나가는 길이지 둑이 끊긴 곳이 아니다: 16m 미만의 틈은 메운다
    land = unary_union(rail).buffer(8).buffer(-8)
    cl = LineString([(x, center_y(x)) for x in (-240, 270)])
    # 둑 폭: 중심선에서 남북으로 25m(카카오 지도에서 지하보도 띠가 도로 끝에서 도로 끝까지 약 50m). 지적 철도용지는 서쪽에서 북쪽 도로를 20m 넘게 덮는다.
    land = land.intersection(box(-230, FOOT_Y, 260, 100)).intersection(cl.buffer(HALF_W, cap_style=2))
    band = cl.buffer(11, cap_style=2)
    slope_zone = unary_union([box(-230, FOOT_Y, 100, 100), cl.buffer(32, cap_style=2)])
    slope = land.intersection(slope_zone)
    deck = land.intersection(band)

    # 굴다리 통로: (이름, 도로 모양, 통로 높이)
    cut_road = box(-58, 0, -33, 100)      # 연세로(폭 약 25m). 카카오 지도의 도로면 경계에서 읽음
    # 신촌 토끼굴은 위치를 확인하지 못해 아직 만들지 않는다(지적도의 82-17 보행로 필지를 통로로 뚫었더니 논지당 위 선로가 끊겨 보여 뺐다).
    unders = [("연세로 굴다리", cut_road, CLEAR_ROAD)]

    # 지하보도(보행 터널): 지도의 '지하보도' 띠(폭 약 4.5m, 남북으로 둑 밑을 관통). 둑 위는 그대로 덮고 아래쪽 입구만 3m 높이로 뚫는다.
    TUN_W, TUN_H = 4.5, 3.0
    tunnels = [box(cx - TUN_W / 2, FOOT_Y - 1, cx + TUN_W / 2, 100) for cx in (-72.7, -21.0)]  # 서쪽(길 건너) / 동쪽(일심약국 옆)
    T = unary_union(tunnels)
    TUN_C = (-72.7, -21.0)
    PORTAL_H, PORTAL_W, PORTAL_D = 4.6, 9.6, 3.0     # 입구 벽(로드뷰: 평평한 콘크리트 벽이 입구 위로 약 4.5m)

    out = []

    def add(g, b, h, c, k):
        if g.is_empty:
            return
        for gg in (g.geoms if hasattr(g, "geoms") else [g]):
            if gg.geom_type != "Polygon" or gg.area < 0.5:
                continue
            gg = gg.simplify(0.2)
            out.append({"type": "Feature", "properties": {"b": b, "h": h, "c": c, "k": k},
                        "geometry": json.loads(json.dumps(mapping(to_ll(gg))), parse_float=lambda s: round(float(s), 7))})

    solid_deck, solid_slope = deck, slope
    for name, u, clr in unders:
        hole = u.intersection(land)
        solid_deck = solid_deck.difference(u)
        solid_slope = solid_slope.difference(u)
        add(hole.intersection(band), clr, DECK_H, COL["lintel"], "lintel")                 # 선로대 아래를 지나는 통로 위 상판
        add(hole, 0, 0.12, COL["floor"], "floor")                                           # 통로 바닥(길)
        print(f"{name}: 통로 면적 {hole.area:.0f} m², 선로대 겹침 {hole.intersection(band).area:.0f} m²")

    n = int(DECK_H / (SLOPE_K * STEP_E)) + 1
    for i in range(1, n + 1):
        h = min(DECK_H, SLOPE_K * STEP_E * i)
        P, col = solid_slope.buffer(-(i - 1) * STEP_E), (WALL_COL if h < 7.8 else GREEN_COL)
        add(P.difference(T), 0, round(h, 2), col, "slope")
        if h > TUN_H:
            add(P.intersection(T), TUN_H, round(h, 2), col, "slope")                         # 터널 위 흙(입구 높이 3m 위)
    add(solid_deck.difference(T), 0, DECK_H, COL["deck"], "deck")
    add(solid_deck.intersection(T), TUN_H, DECK_H, COL["deck"], "deck")
    add(T.intersection(land), 0, 0.12, COL["floor"], "floor")                                # 터널 바닥
    for cx in TUN_C:                                                                         # 입구 벽: 터널 양 끝(남·북)에 평평한 벽을 세우고 3m 높이 개구부를 낸다
        strip = box(cx - TUN_W / 2, FOOT_Y - 1, cx + TUN_W / 2, 100).intersection(land)
        y0, y1 = strip.bounds[1], strip.bounds[3]
        print(f"지하보도 x={cx}: 터널 길이 {y1 - y0:.0f} m (y {y0:.0f}~{y1:.0f})")
        for ya, yb in ((y0, y0 + PORTAL_D), (y1 - PORTAL_D, y1)):
            B = box(cx - PORTAL_W / 2, ya, cx + PORTAL_W / 2, yb).intersection(land)
            add(B.difference(T), 0, PORTAL_H, WALL_COL, "portal")
            add(B.intersection(T), TUN_H, PORTAL_H, WALL_COL, "portal")
    # 선로 5줄
    for off in (-8.4, -4.2, 0, 4.2, 8.4):
        line = LineString([(x, center_y(x) + off) for x in (-240, 270)]).buffer(0.9, cap_style=2)
        add(line.intersection(land), DECK_H, DECK_H + 0.25, COL["rail"], "rail")

    OUT.write_text(json.dumps({"type": "FeatureCollection", "features": out}, ensure_ascii=False))
    from collections import Counter
    print("features", len(out), dict(Counter(f["properties"]["k"] for f in out)), f"{OUT.stat().st_size/1024:.0f} KB")


if __name__ == "__main__":
    main()
