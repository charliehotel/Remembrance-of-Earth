"""지도 페이지(web/)가 읽을 단일 JSON을 만든다: web/scene.json

- parcels: 필지 폴리곤 + 필지 속성
- buildings: 현존 건물 폴리곤. start(사용승인 연도), height(m), height_basis(대장/층수추정), flags
  * 날짜 없고 높이·층수도 0인 부속물은 제외(excluded 에 개수)
  * 사용승인 연도가 1990 이전인 건물(B005 1970, B108 1938, B095 1973)은 옛 대장 흔적일 수 있어 flag=old_date
- businesses: 필지별 업소 구간(timeline_businesses.csv). 시간 엔진이 연도로 걸러 쓴다.
- building_events: 필지별 말소·철거 이력(폴리곤 없음, 팝업 설명용)
사용: .venv/bin/python -I scripts/export_web.py
"""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# 대장·필지와 맞지 않아 제외: B025는 브이월드에만 있고(승인 1994-02-05, 대지 247.03㎡) 건축HUB 대장에 없으며,
# 도형이 2-46·2-44·2-45 경계에 걸쳐 필지 확정 불가. 2-46 대장은 2003년 학림빌딩 1채뿐.
EXCLUDE_BIDS = {"B025"}
LANDMARK_START = {"B098": 1906}  # 창천감리교회 본당
OUT = ROOT / "web"

# ---- 랜드마크 매싱(사진 기반 근사). 대장 외곽선(필지 폴리곤)을 부위별로 잘라 높이·색을 달리한다.
import math
from shapely.geometry import Polygon, box as sbox, shape
from shapely.affinity import rotate as srot
KX, KY = 111320 * math.cos(math.radians(37.559)), 110540


def _loc(poly, o):
    return Polygon([((x - o[0]) * KX, (y - o[1]) * KY) for x, y in poly])


def _geo(g, o):
    out = []
    for gg in (g.geoms if hasattr(g, "geoms") else [g]):
        if gg.is_empty or gg.area < 0.03:
            continue
        out.append([[o[0] + x / KX, o[1] + y / KY] for x, y in gg.exterior.coords])
    return out


def massing(bid, ring):
    """[(polygon coords, base, top, color)] 또는 None. 사진 관찰 기반 근사 형상(높이 근거는 대장 최고높이)."""
    from shapely.geometry import Point, LineString
    o = ring[0]
    P = _loc(ring, o)
    BR, BR2, STONE, ROOF, SPIRE = "#9c4f3c", "#8a4332", "#ddd6c6", "#7c8a78", "#4c6a58"
    parts = []
    add = lambda g, b, t, c: parts.append((g, b, t, c))
    inP = lambda x0, y0, x1, y1: P.intersection(sbox(x0, y0, x1, y1))
    if bid == "B098":  # 창천교회. 정면(쌍탑)은 서쪽 짧은 변. 본당 장변 약 43m, 정면 폭 약 24m
        NAVE, GAB, SH, BEL = 14.0, 17.5, 19, 21.5
        from shapely.affinity import translate
        # 정면 배치(사진): 쌍탑 앞면(x=0.2) > 중앙 벽(탑 사이, 안쪽으로 물러남 x=WX, 두께 WT 로 아주 얇다) < 석재 현관(앞면 x=PX).
        WX, PX, WT = 1.8, -1.4, 1.2
        YC = 12.1
        add(inP(6.6, -3, 50, 30), 0, NAVE, BR)                                 # 본당 벽체(탑 뒤쪽)
        add(inP(WX + WT, YC - 6.3, 6.6, YC + 6.3), 0, NAVE, BR2)               # 탑 사이 빈 공간 채움(지붕 아래)
        # 맞배지붕(위성사진: 녹색): 용마루가 동서 방향이고 남·북으로만 경사지며 동·서 끝은 수직 박공이다.
        # y 방향으로만 줄이려고 R 을 ±d 만큼 y 로 밀어 겹친다(= y 침식). 외곽선 4면을 모두 줄이는 buffer 는 우진각이 된다.
        RF = P.intersection(sbox(WX, -10, 60, 40))                              # 지붕 단면 윤곽 기준 영역
        nb = inP(6.6, -10, 60, 40).bounds                                       # 본당 폭 기준(탑 구간 제외)
        hwid = (nb[3] - nb[1]) / 2
        NR = 8
        ds = [0.25 + i * (hwid - 0.4 - 0.25) / (NR - 1) for i in range(NR)]    # 마지막 단은 용마루 폭 약 0.8m
        roofR = P.intersection(sbox(WX + WT, -10, 60, 40)).intersection(
            sbox(6.6, -10, 60, 40).union(sbox(WX + WT, YC - 6.3, 6.6, YC + 6.3)))   # 탑 구간(x<6.6)에서는 탑 사이 폭만
        def erode_y(g, d):
            return g.intersection(translate(g, 0, d)).intersection(translate(g, 0, -d))
        for i, d in enumerate(ds):
            g = erode_y(RF, d).intersection(roofR)
            if not g.is_empty:
                add(g, NAVE + 0.8 * i, NAVE + 0.8 * (i + 1), ROOF)
        # 측면 벽의 창·부벽: 탑 안쪽 면(TX0)부터 동쪽 벽 끝까지를 8등분해 칸마다 창 1개를 가운데에 둔다.
        # 그러면 창 간격이 모두 같고 양끝 여백(칸 폭 - 창 폭)/2 도 같다. 남·북 벽 길이가 달라 칸 폭은 면마다 따로 계산한다.
        TX0 = 6.6                                                               # 탑 안쪽 면(탑 cx 2.2 + hx 4.4)
        SIDES = {"S": (43.5, (-10, 12)), "N": (42.8, (12, 40))}                 # 면: (동쪽 벽 끝 x, 창을 자를 y 구간) — 대장 외곽선 꼭짓점 11, 6
        PITCH = {k: (v[0] - TX0) / 8 for k, v in SIDES.items()}
        # 양 측면 소첨탑: 남·북 모두 9개. 창 사이 칸 경계 7곳 + 양끝 2곳(탑·동쪽 벽에서 띄워 묻히거나 삐져나오지 않게).
        # 기둥은 지붕 가장자리에서 0.9m 들여 놓고(폭 0.9m 이므로 가장자리와 0.45m 이상 떨어짐), 지붕 첫 단 안쪽으로 한 번 더 잘라 둔다.
        inner = P.buffer(-0.9)
        roof0 = P.buffer(-0.3)

        def pyramid(cx, cy, z0, hw, shaft, tip, clip=None, n=5):
            """사각기둥(높이 shaft) 위에 사각뿔(높이 tip)을 n단 계단으로 쌓는다. 밑면 반폭 hw, 꼭대기는 hw/(n+1)."""
            def put(g, b, t):
                g = g if clip is None else g.intersection(clip)
                if not g.is_empty:
                    add(g, b, t, STONE)
            put(sbox(cx - hw, cy - hw, cx + hw, cy + hw), z0, z0 + shaft)
            dz = tip / n
            for i in range(n):
                w = max(hw * (1 - (i + 0.5) / n), 0.06)
                put(sbox(cx - w, cy - w, cx + w, cy + w), z0 + shaft + i * dz, z0 + shaft + (i + 1) * dz)
        for key, (xe, _) in SIDES.items():
            xs = [TX0 + 1.0] + [TX0 + PITCH[key] * k for k in range(1, 8)] + [xe - 1.4]
            for x in xs:
                seg = inner.intersection(LineString([(x, -10), (x, 40)]))
                if seg.is_empty:
                    continue
                _, y0, _, y1 = seg.bounds
                y = y0 if key == "S" else y1
                pyramid(x, y, NAVE, 0.45, 0.8, 1.5, roof0)
        # 외곽선 서쪽 변은 비스듬하고 포치 등이 섞여 있어, 중앙 벽·현관은 외곽선이 아니라 WX/PX 값으로 직사각형을 만든다.
        wall = sbox(WX, YC - 6.3, WX + WT, YC + 6.3)                            # 정면 중앙부(탑 사이) 벽: 탑보다 1.6m 뒤, 두께 1.2m
        add(wall, 4.2, NAVE, BR2)
        for i, d in enumerate(ds):                                              # 정면 박공: 지붕 단면과 같은 계단 윤곽(꼭대기 = 용마루 높이)
            g = erode_y(RF, d).intersection(wall)
            if not g.is_empty:
                add(g, NAVE + 0.8 * i, NAVE + 0.8 * (i + 1), BR2)
        # 현관(사진 분석): 두 탑 사이 틈 중심 YC=12.1을 기준으로 좌우 대칭. 뾰족 아치 3개(폭 3.3m, 도약선 1.9m, 꼭대기 3.0m), 위에 3.1~4.5m 띠
        PB = sbox(PX, YC - 6.3, WX, YC + 6.3)                                   # 현관 석재 덩어리(폭 12.6m, 깊이 3.2m). 외곽선으로 자르지 않는다
        CEN = (YC + 4.1, YC, YC - 4.1)                                          # 북·가운데·남 아치 중심(남쪽 = 문 쪽)
        def openings(h0, h1):                                                   # 높이 구간별 아치 개구부(깊이 약 2.6m)
            if h1 <= 1.9:
                hw = 1.65
            else:
                k = min(3, max(0, int((h0 - 1.9) / (1.1 / 3))))
                hw = 1.65 * (1 - (k + 0.6) / 4.2)
            return [sbox(-5, c - hw, 1.0, c + hw) for c in CEN]
        bands = [(0, 1.9)] + [(1.9 + i * 1.1 / 3, 1.9 + (i + 1) * 1.1 / 3) for i in range(3)]
        for h0, h1 in bands:
            g = PB
            for o_ in openings(h0, h1):
                g = g.difference(o_)
            add(g, h0, h1, STONE)
        add(PB, 3.0, 4.5, STONE)                                                # 아치 위 띠
        add(PB.buffer(-0.35), 4.5, 4.9, STONE)                                  # 난간
        for c in CEN:                                                           # 개구부 안쪽 어두운 바닥판(깊이감)
            add(sbox(0.7, c - 1.6, 1.0, c + 1.6).intersection(PB.buffer(0.05)), 0.05, 1.9, "#2a2622")
            for i in range(3):
                hw = 1.6 * (1 - (i + 0.6) / 4.2)
                add(sbox(0.7, c - hw, 1.0, c + hw).intersection(PB.buffer(0.05)), 1.9 + i * 0.37, 1.9 + (i + 1) * 0.37, "#2a2622")
        for c in CEN:                                                           # 아치 위 삼각 박공(돌출 0.18m, 회색 음영)
            for i, hw in enumerate((1.7, 1.3, 0.9, 0.5)):
                add(sbox(-5, c - hw, 1.0, c + hw).intersection(PB.buffer(0.18)), 3.1 + i * 0.35, 3.1 + (i + 1) * 0.35, "#cfc8b8")
        for y in (YC - 6.0, YC - 2.05, YC + 2.05, YC + 6.0):                    # 소첨탑 4개(아치 사이·양끝): 현관 앞면 위
            for b0, b1, hw in ((4.5, 5.2, 0.28), (5.2, 5.7, 0.16)):
                add(PB.buffer(0.1).intersection(sbox(-5, y - hw, PX + 1.0, y + hw)), b0, b1, STONE)
        # 큰 창(사진 2장 서브에이전트 분석): 외벽선을 따라 얇게 돌출한 띠로 그린다. 흰 틀이 뒤, 유리가 앞.
        FR = P.buffer(0.28).difference(P.buffer(-0.05))       # 틀 층
        GL = P.buffer(0.40).difference(P.buffer(-0.05))       # 유리 층(틀보다 0.12m 앞)
        FRF = sbox(WX - 0.28, 0, WX + 0.05, 2 * YC)           # 정면 중앙 벽 위 틀 층(물러난 벽면 x=WX 에 붙임)
        GLF = sbox(WX - 0.40, 0, WX + 0.05, 2 * YC)           # 정면 유리 층
        def lancet(cut, w, sill, spring, top, glass, rim=0.18, n=4, fr=None, gl=None):
            # 뾰족 아치 창: 아치 시작점까지 직사각형, 그 위는 n단으로 좁혀 끝을 뾰족하게
            fr = FR if fr is None else fr
            gl = GL if gl is None else gl
            add(fr.intersection(cut(w / 2 + rim)), sill - rim, spring, "#f0eee8")
            add(gl.intersection(cut(w / 2)), sill, spring, glass)
            dh = (top - spring) / n
            for i in range(n):
                hw = (w / 2) * (1 - (i + 1) / (n + 1))
                add(fr.intersection(cut(hw + rim)), spring + i * dh, spring + (i + 1) * dh + (rim if i == n - 1 else 0), "#f0eee8")
                add(gl.intersection(cut(hw)), spring + i * dh, spring + (i + 1) * dh, glass)
        side = lambda xc, ylo, yhi: (lambda h: sbox(xc - h, ylo, xc + h, yhi))
        for key, (_, (ylo, yhi)) in SIDES.items():             # 측면: 칸 가운데마다 큰 뾰족 창 1개(8개), 남·북 양쪽
            for k in range(8):
                xc = TX0 + PITCH[key] * (k + 0.5)
                lancet(side(xc, ylo, yhi), 2.2, 4.0, 9.0, 11.5, "#2b3a38")
        front = lambda yc: (lambda h: sbox(-5, yc - h, 9, yc + h))
        # 정면 중앙벽: 흰 뾰족 아치 테두리 안에 큰 창 2개 + 장미창(모두 물러난 벽면 x=WX 위)
        for i, (b0, b1, hw) in enumerate(((4.8, 10.5, 2.65), (10.5, 11.6, 2.25), (11.6, 12.4, 1.6), (12.4, 13.0, 0.8))):
            add(FRF.intersection(front(YC)(hw)), b0, b1, "#e8e4d8")
        for yc in (YC - 1.25, YC + 1.25):
            lancet(front(yc), 1.9, 4.9, 8.3, 10.4, "#2e3b45", rim=0.12, n=3, fr=FRF, gl=GLF)
        for b0, b1, hw in ((10.9, 11.25, 0.5), (11.25, 12.3, 0.85), (12.3, 12.65, 0.5)):   # 장미창(지름 1.7m, 원을 3단으로 근사)
            add(GLF.intersection(front(YC)(hw)), b0, b1, "#5e8f8a")
        for cy, hy in ((2.85, 2.95), (21.35, 2.95)):                            # 쌍탑: 안쪽 면을 현관 경계(YC±6.3 = 5.8·18.4)에 맞춘다(전엔 8.5·15.7까지 먹고 들어와 현관 아치를 막고 돌조각이 튀어나옴)
            # 두 탑은 같은 크기의 직사각형(6.4×5.1m)이고 현관 중심선 YC 를 기준으로 좌우 대칭이다.
            # 크기는 외곽선 안에 들어가는 남탑 기준. 외곽선 서쪽 변은 포치 등 돌출부가 섞여 비스듬해서 탑 모양 근거로 쓰지 않는다.
            x0, x1 = 0.2, 6.6
            y0, y1 = (0.7, 5.8) if cy < 12 else (2 * YC - 5.8, 2 * YC - 0.7)
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            assert P.buffer(0.05).contains(sbox(x0, y0, x1, y1)), (x0, y0, x1, y1)
            add(sbox(x0, y0, x1, y1), 0, SH, BR)                                # 탑 몸체
            add(sbox(x0 + .5, y0 + .5, x1 - .5, y1 - .5), SH, BEL, BR2)         # 종탑부
            for px in (x0 + .5, x1 - .5):                                       # 모서리 소첨탑 4개(R 안쪽 모서리)
                for py in (y0 + .5, y1 - .5):
                    pyramid(px, py, SH, 0.5, 3.0, 1.7)
            w0 = min(x1 - x0, y1 - y0) / 2 - 0.9                                # 첨탑 밑면: 종탑부 안쪽에 들어가게
            for i in range(6):                                                  # 뾰족한 녹청 첨탑(단 지붕)
                w = w0 * (1 - i / 6.0) + 0.2
                add(sbox(cx - w, cy - w, cx + w, cy + w), BEL + i * 0.85, BEL + (i + 1) * 0.85, SPIRE)
            top = BEL + 6 * 0.85                                                # 십자가(꼭대기 29.1m = 대장 최고높이)
            add(sbox(cx - .17, cy - .17, cx + .17, cy + .17), top, 29.1, "#e6e6e6")        # 세로대
            add(sbox(cx - .17, cy - .9, cx + .17, cy + .9), top + 1.35, top + 1.85, "#e6e6e6")  # 가로대(정면 방향 폭)
    elif bid == "B078":  # 아웃백(사진 3장 분석). 동서로 긴 건물(≈28m×10m). 서쪽은 옆 건물과 붙어 있음.
        # 사진의 짧은 변 = 동쪽, 길쭉한 정면 = 남쪽, 후면(주차장) = 북쪽(사용자 확인).
        # 아래 식은 '짧은 변 = x0'으로 썼으므로 동서를 뒤집어 계산한 뒤 다시 뒤집는다.
        from shapely import affinity
        _add = add
        add = lambda g, b, t, c: _add(affinity.scale(g, xfact=-1, origin=(0, 0)), b, t, c)
        P = affinity.scale(P, xfact=-1, origin=(0, 0))
        x0, y0, x1, y1 = P.bounds
        L, yc = x1 - x0, (y0 + y1) / 2
        SID, RED, TRIM = "#dcc7a1", "#a5503a", "#e8d6b0"
        add(P.buffer(-0.2), 3.6, 6.9, SID)                                     # 2층: 베이지 사이딩
        add(P.buffer(0.55).difference(P.buffer(-0.2)).intersection(P.buffer(0.55)), 6.9, 7.35, RED)   # 붉은 차양 띠(돌출 0.6m)
        add(P.buffer(-0.2), 6.9, 7.35, SID)
        add(P.buffer(-0.6), 7.35, 8.0, RED)                                    # 붉은 금속 경사지붕(2단 근사)
        add(P.buffer(-1.8), 8.0, 8.7, RED)
        up = P.buffer(-1.0)
        for b2, t2, hw in ((7.35, 9.0, 3.9), (9.0, 10.5, 3.2), (10.5, 12.0, 2.4), (12.0, 13.5, 1.8)):   # 뒤쪽 높은 벽: 단면 오각형, 길이 방향으로 기운다
            mid = (b2 + t2) / 2
            xe = max(x0 + 3.5, x0 + (13.5 - mid) / 4.5 * L) if t2 > 9.0 else x1
            add(up.intersection(sbox(x0, yc - hw, xe, yc + hw)), b2, t2, "#e3cda6")
        RIM = "#c8102e"   # 아웃백 상징: 빨간 테두리 삼각형(박공)
        band = P.buffer(0.35).difference(P.buffer(0.05))   # 실제 외벽선을 따라 바로 바깥 띠(대지 경계가 비스듬함)
        def gable(axis, c, hw, bot, top, f0, f1, n=16, rim=0.42):
            # 촘촘한 계단으로 채운 삼각형 + 바깥면에 빨간 테두리(양쪽 빗변 + 밑변)
            dh = (top - bot) / n
            for i in range(n):
                h, w = bot + i * dh, hw * (1 - i / n)
                box = (lambda u0, u1, v0, v1: sbox(v0, u0, v1, u1)) if axis == "x" else (lambda u0, u1, v0, v1: sbox(u0, v0, u1, v1))
                add(P.buffer(0.1).intersection(box(c - w, c + w, f0 - 1.5, f1)), h, h + dh, TRIM)
                for s0, s1 in ((c - w, c - w + rim), (c + w - rim, c + w)):
                    add(band.intersection(box(s0, s1, f0 - 1.5, f0 + 2.5)), h, h + dh + .05, RIM)
            add(band.intersection(box(c - hw, c + hw, f0 - 1.5, f0 + 2.5)), bot, bot + .3, RIM)
        gable("x", yc, 4.2, 7.35, 11.0, x0 - .05, x0 + 2.2)          # 동쪽 짧은 변 큰 삼각형
        gable("y", x0 + 8.5, 2.8, 7.35, 9.8, y0 - .05, y0 + 2.2, n=12)  # 남쪽 정면 작은 삼각형
        add(P.intersection(sbox(x0 - .2, y0 - .3, x0 + 5.5, yc - 1.0)), 0, 3.6, SID)  # 1층 닫힌 코어 벽(폭 ≈5.5m)
        for k in range(5):                                                      # 남쪽 필로티 기둥 5개 + 북쪽(주차장) 3개
            for yy, ok in ((y0 + 1.0, True), (y1 - 1.5, k % 2 == 0)):
                if not ok:
                    continue
                cx = x0 + 6.5 + k * 5.0
                add(sbox(cx - .3, yy - .3, cx + .3, yy + .3).intersection(P.buffer(0.2)), 0, 3.6, "#d4bc98")
                add(sbox(cx - .31, yy - .31, cx + .31, yy + .31).intersection(P.buffer(0.2)), 0, 1.0, "#3a3a3a")   # 노랑·검정 도색 대신 어두운 하단부
        add(P.buffer(-0.2), 0, 0.1, "#8a8a8a")
    elif bid == "B042":  # 창천교회 백주년기념관: 필로티 1층 + 정면(남) 유리 커튼월 + 남동 모서리 계단실 유리 + 나머지 석재 타일
        # 높이: 대장 24.45m 는 본당 용마루(≈20.4m)보다 높게 그려져 로드뷰와 어긋난다. 지상 5층으로 17.3m 를 쓴다.
        H0, H1, H2, H3 = 3.6, 4.7, 16.2, 17.3
        TILE, STONE, GLASS, SPAN, WIN = "#c98f78", "#c9a98c", "#6f9fc4", "#a9b7c0", "#3f5f7a"
        NF = 4
        FL = [H1 + (H2 - H1) * i / NF for i in range(NF + 1)]                  # 4개 층 경계(필로티 위 슬래브 제외)
        stair = inP(-2.6, -3.6, 0.8, 0.9)                                       # 남동 모서리 둥근 계단실
        front = inP(-17, -6, -2.1, -2.0).intersection(                          # 정면(남쪽 변) 유리: 변을 따라 약 1m 깊이
            Polygon([(-17, -6), (-2.1, -6), (-2.1, -2.1), (-15.0, -3.2), (-17, -3.4)])).difference(stair)
        body = P.difference(front.union(stair))
        add(P, H0, H1, STONE)                                                   # 필로티 위 석재 띠(간판 자리)
        add(body, H1, H2, TILE)                                                 # 타일 벽체
        # 옥상: 진한 녹색(위성사진). 난간은 가장자리 고리만 세우고, 계단실과 겹치는 부분은 빼서 면이 겹쳐 깜박이지 않게 한다.
        inner = P.buffer(-0.45)
        add(P.difference(inner).difference(stair), H2, H3, STONE)               # 난간 고리
        add(inner.difference(stair), H2, H2 + 0.12, "#2f5a35")                  # 옥상 녹지
        add(stair, H1, H3 + 0.5, "#35597a")                                     # 계단실 유리(난간보다 조금 높게)
        add(stair, H3 + 0.5, H3 + 0.7, STONE)                                   # 계단실 지붕
        for i in range(NF):                                                     # 정면 유리: 층마다 창 + 얇은 스팬드럴 띠
            add(front, FL[i], FL[i + 1] - 0.35, GLASS)
            add(front, FL[i + 1] - 0.35, FL[i + 1], SPAN)
        cs = list(P.exterior.coords)[:-1]
        edges = [(cs[k], cs[(k + 1) % len(cs)]) for k in range(len(cs))]
        def side_edge(want):                                                    # 방위별로 가장 긴 외곽 변: (시작, 끝, 바깥 법선)
            best = None
            for (ax, ay), (bx, by) in edges:
                L = LineString([(ax, ay), (bx, by)]).length
                if L < 4:
                    continue
                nx, ny = (by - ay) / L, -(bx - ax) / L
                mx, my = (ax + bx) / 2, (ay + by) / 2
                if P.contains(Point(mx + nx * 0.05, my + ny * 0.05)):
                    nx, ny = -nx, -ny
                if (nx, ny) and {"W": nx < -.6, "E": nx > .6, "N": ny > .6, "S": ny < -.6}[want]:
                    if best is None or L > best[0]:
                        best = (L, (ax, ay), (bx, by), (nx, ny))
            return best
        def strip(e, t0, t1, b, t, col, TH=0.12):                               # 변 위의 얇은 판(창): 변 길이의 t0~t1 구간
            _, (ax, ay), (bx, by), (nx, ny) = e
            ux, uy = bx - ax, by - ay
            q0 = (ax + ux * t0, ay + uy * t0)
            q1 = (ax + ux * t1, ay + uy * t1)
            add(Polygon([q0, q1, (q1[0] + nx * TH, q1[1] + ny * TH), (q0[0] + nx * TH, q0[1] + ny * TH)]), b, t, col)
        # 서쪽 측면(본당과 마주한 변): 층마다 세로로 긴 창 2개 = 8개
        W = side_edge("W")
        for i in range(NF):
            for tc in (0.36, 0.66):
                hw = 0.55 / W[0]
                strip(W, tc - hw, tc + hw, FL[i] + 0.45, FL[i + 1] - 0.45, WIN)
        # 북쪽 뒷면(사진 4): 본당 쪽(서쪽 끝)에 4개 층 큰 유리 커튼월, 그 옆에 폭 0.5m 세로 유리 띠, 나머지는 타일
        N = side_edge("N")
        if N:
            for i in range(NF):
                strip(N, 0.0, 0.46, FL[i] + 0.1, FL[i + 1] - 0.35, GLASS)
                strip(N, 0.0, 0.46, FL[i + 1] - 0.35, FL[i + 1], SPAN)
            hw = 0.25 / N[0]
            strip(N, 0.62 - hw, 0.62 + hw, H1 + 0.3, H2 - 0.3, GLASS)
        # 동쪽 측면: 유리창이 많다 — 층마다 세로 창 4개를 촘촘히
        E = side_edge("E")
        if E:
            for i in range(NF):
                for tc in (0.2, 0.4, 0.6, 0.8):
                    hw = 0.6 / E[0]
                    strip(E, tc - hw, tc + hw, FL[i] + 0.45, FL[i + 1] - 0.45, WIN)
        ex = P.buffer(-0.8).exterior
        for x, y in list(P.exterior.coords)[:-1]:                               # 필로티 기둥
            c = ex.interpolate(ex.project(Point(x, y)))
            add(sbox(c.x - .6, c.y - .6, c.x + .6, c.y + .6), 0, H0, STONE)
    else:
        return None
    out = []
    for g, b, t, col in parts:
        for ring2 in _geo(g, o):
            out.append((ring2, b, t, col))
    return out


def rc(p):
    return list(csv.DictReader(open(ROOT / p, encoding="utf-8-sig")))


# ---- 공사 기간(건축HUB 대장). 착공~사용승인 동안 크레인과 함께 건물이 올라간다. 날짜 단위는 소수 연도.
import datetime
HUB = ROOT / "data/raw/hub"
_hub = lambda n: json.loads((HUB / f"{n}.json").read_text())
BR, AP, SR, DEMOL = _hub("br_title"), _hub("ap_basis"), _hub("sr_title"), _hub("ap_demol")
MIN_BUILD = 0.5   # 착공~승인이 이보다 짧으면 승인 0.5년 전부터 올린다
FALLBACK = 1.0    # 대장에 날짜가 없으면 승인 1년 전부터(가정)


def yf(s):
    """YYYYMMDD(일·월이 00이면 중순) → 소수 연도. 빈 값은 None."""
    s = (s or "").strip()
    if len(s) != 8 or not s.isdigit():
        return None
    y, m, d = int(s[:4]), int(s[4:6]) or 6, int(s[6:]) or 15
    return round(y + (datetime.date(y, m, d).timetuple().tm_yday - 1) / 365.25, 3)


def iso(s):
    s = (s or "").strip()
    return f"{s[:4]}-{s[4:6]}-{s[6:]}" if len(s) == 8 else ""


def phase(jibun, approved8):
    """현존 건물 → (a, b, a_iso, b_iso, 근거). 승인일이 1993 이전(1992 이전 포함)이어도 계산한다."""
    ya = yf(approved8)
    cand = [r for r in BR.get(jibun) or [] if yf(r["useAprDay"]) and abs(yf(r["useAprDay"]) - ya) < 1.2]
    cand.sort(key=lambda r: (not r["pmsDay"].strip(), abs(yf(r["useAprDay"]) - ya)))
    if not cand:
        if ya < 1993:
            return None
        return round(ya - FALLBACK, 3), ya, "", iso(approved8), "대장에 공사 날짜 없음: 사용승인 1년 전부터 가정"
    r = cand[0]
    b = yf(r["useAprDay"])
    st = r["stcnsDay"].strip()
    if not yf(st):  # 표제부에 착공일이 없으면 인허가 기본개요의 실착공일
        st = next((q.get("realStcnsDay", "") for q in AP.get(jibun) or []
                   if q["archGbCdNm"].strip() == "신축" and yf(q.get("realStcnsDay", ""))), "")
    if yf(st):
        a, basis, ai = yf(st), "착공일~사용승인일", iso(st)
    elif yf(r["pmsDay"]):
        a, basis, ai = yf(r["pmsDay"]), "허가일~사용승인일(착공일 없음)", iso(r["pmsDay"])
    else:
        return round(b - FALLBACK, 3), b, "", iso(r["useAprDay"]), "대장에 공사 날짜 없음: 사용승인 1년 전부터 가정"
    if b - a < MIN_BUILD:
        a, basis = round(b - MIN_BUILD, 3), basis + ", 공사기간이 짧아 6개월로 늘려 표시"
    return a, b, ai, iso(r["useAprDay"]), basis


# ---- 철거된 옛 건물. 모양 정보는 없으므로 대장의 구조(목구조/벽돌)로 종류만 정해 필지 안쪽 윤곽에 세운다.
GHOST = {"2-2": "tile", "2-23": "slab", "2-46": "tile", "2-6": "tile", "47-39": "slab"}
GHOST_COL = {"tile": ["#a56f52", "#9a6a4a", "#b07a58"], "slab": ["#cdc6b9", "#bdb4a4", "#d3c8b5"]}
GHOST_AREA = {"2-2": 82, "2-23": 59, "2-46": 64, "2-6": 125, "47-39": 109}  # 철거·말소 대장의 연면적(㎡). 단층이라 바닥면적으로 본다
DEMOL_KEY = {"47-39": "47-2"}   # 철거멸실대장에는 분할 전 지번(47-2)으로 올라 있다


def ghosts(parcel_geoms, new_start):
    """new_start: 필지 → 새 건물 착공(a). 철거 시점 = 철거 기간(있으면) / 아니면 min(말소일, 착공 0.25년 전)."""
    feats, info = [], {}
    for jib, kind in GHOST.items():
        a = new_start.get(jib)
        if a is None or jib not in parcel_geoms:
            continue
        dm = [r for r in DEMOL.get(DEMOL_KEY.get(jib, jib)) or [] if yf(r["demolStrtDay"])]
        if dm and jib not in ("2-46", "2-6", "2-23"):
            ds, de = yf(dm[0]["demolStrtDay"]), yf(dm[0]["demolEndDay"]) or yf(dm[0]["demolStrtDay"])
            basis = "철거멸실대장의 철거 기간"
        else:
            sh = [yf(r["shterDay"]) for r in SR.get(jib) or [] if yf(r["shterDay"])]
            de = min([a - 0.25] + sh)
            ds, basis = de - 0.12, ("말소일" if sh and min(sh) < a - 0.25 else "새 건물 착공 직전") + " 이전"
        ds = min(ds, de - 0.12)   # 철거 장면이 화면에서 보이도록 최소 약 1.5개월
        g = parcel_geoms[jib]
        o = g.centroid.coords[0]
        loc = _loc(list(g.exterior.coords), o) if g.geom_type == "Polygon" else _loc(list(max(g.geoms, key=lambda x: x.area).exterior.coords), o)
        fp = loc.buffer(-1.3)
        if fp.is_empty or fp.area < 15:
            fp = loc.buffer(-0.5)
        if fp.area > GHOST_AREA[jib]:  # 대장 규모에 맞춰 필지 중심 쪽으로 줄인다
            from shapely.affinity import scale as sscale
            k = math.sqrt(GHOST_AREA[jib] / fp.area)
            fp = sscale(fp, k, k, origin=fp.centroid)
        col = GHOST_COL[kind][sum(map(ord, jib)) % 3]
        if kind == "tile":   # 박공 지붕은 계단식 박스로 근사: 벽 3.2m + 지붕 2단
            layers = [(fp, 0, 3.2, col), (fp.buffer(-1.0), 3.2, 4.2, "#6f4a38"), (fp.buffer(-2.2), 4.2, 5.0, "#6f4a38")]
        else:
            layers = [(fp, 0, 3.6, col), (fp.buffer(-0.5), 3.6, 4.1, "#9d9486")]
        for part, (poly, b0, t0, c0) in enumerate(layers):
            for ring in _geo(poly, o):
                feats.append({"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [ring]},
                              "properties": {"jibun": jib, "kind": kind, "base": b0, "top": t0, "color": c0, "dstart": ds, "dend": de}})
        info[jib] = {"kind": kind, "dend": de, "basis": basis}
    return {"type": "FeatureCollection", "features": feats}, info


# ---- 주변 맥락 지도: 창천교회(지오코딩 지점) 반경 300m 안의 연속지적도 필지. 아직 구현하지 않은 곳이라 흐리게만 그린다.
CONTEXT_RADIUS_M = 300
CONTEXT_BLD_RADIUS_M = 150  # 회색 주변 건물은 이 반경 안만


def context_map(core_pnus):
    import re
    from shapely.geometry import Point, mapping
    gc = json.load(open(ROOT / "data/raw/vworld/geocode_church.json"))["response"]["result"]["items"][0]["point"]
    o = (float(gc["x"]), float(gc["y"]))
    to_m = lambda g: shapely_transform(g, lambda x, y: ((x - o[0]) * KX, (y - o[1]) * KY))
    to_ll = lambda g: shapely_transform(g, lambda x, y: (o[0] + x / KX, o[1] + y / KY))
    circle = Point(0, 0).buffer(CONTEXT_RADIUS_M, 128)
    src = json.load(open(ROOT / "data/raw/vworld/cadastral_bbox.json"))["response"]["result"]["featureCollection"]["features"]
    feats = []
    for f in src:
        p = f["properties"]
        if p["pnu"] in core_pnus:
            continue
        g = to_m(shape(f["geometry"]).buffer(0))
        if not g.intersects(circle):
            continue
        g = g.intersection(circle)
        if g.is_empty or g.area < 1:
            continue
        m = re.match(r"(\S+?)\s*(\D+)$", p["jibun"])
        geo = json.loads(json.dumps(mapping(to_ll(g))), parse_float=lambda s: round(float(s), 7))
        feats.append({"type": "Feature", "geometry": geo,
                      "properties": {"jibun": m.group(1) if m else p["jibun"], "jimok": m.group(2).strip() if m else ""}})
    # 주변 건물: 이미 받아 둔 GIS건물통합정보(연세로12길 주변 띠만 있음) 중 구현 필지 밖, 반경 150m 안에 있는 것. 회색 매스로만 쓴다.
    # 300m 전체를 채우면 너무 복잡해 보여서 건물은 가까운 곳만 두고, 그 바깥은 필지만 흐리게 그린다.
    bld_circle = Point(0, 0).buffer(CONTEXT_BLD_RADIUS_M, 64)
    core = shapely_union([to_m(shape(f["geometry"]).buffer(0)) for f in src if f["properties"]["pnu"] in core_pnus])
    blds, seen = [], set()
    cpath = ROOT / "data/context_colors.json"
    colors = json.loads(cpath.read_text()) if cpath.exists() else {}
    # LT_C_BLDGINFO_r150.json: 교회 반경 150m 박스로 따로 받은 파일(있으면 합친다). 두 파일에 겹치는 건물은 대표점으로 한 번만 쓴다.
    srcs = [ROOT / "data/raw/vworld" / n for n in ("LT_C_BLDGINFO_bbox.json", "LT_C_BLDGINFO_r150.json")]
    bfeats = [f for s in srcs if s.exists() for f in json.load(open(s))["response"]["result"]["featureCollection"]["features"]]
    for f in bfeats:
        g = to_m(shape(f["geometry"]).buffer(0))
        if g.is_empty:
            continue
        rp = g.representative_point()
        key = (round(rp.x, 1), round(rp.y, 1), round(g.area))
        if key in seen or core.contains(rp) or not bld_circle.contains(rp):
            continue
        seen.add(key)
        p = f["properties"]
        h = float(p.get("height") or 0) or (int(p.get("grnd_flr") or 0) * 3.3) or 3.0
        geo = json.loads(json.dumps(mapping(to_ll(g))), parse_float=lambda s: round(float(s), 7))
        props = {"height": round(h, 1)}
        # 지붕색(wc=벽, rc=지붕): scripts/build_context_colors.py 가 위성사진·3D사진에서 만든다. 키는 반올림한 최종 도형 기준.
        ck = colors.get(_ckey(to_m(shape(geo))))
        if ck:
            props.update({k: ck[k] for k in ("wc", "rc") if k in ck})
        blds.append({"type": "Feature", "geometry": geo, "properties": props})
    ring = json.loads(json.dumps(mapping(to_ll(circle.exterior))), parse_float=lambda s: round(float(s), 7))
    return {"center": list(o), "radius_m": CONTEXT_RADIUS_M,
            "parcels": {"type": "FeatureCollection", "features": feats},
            "buildings": {"type": "FeatureCollection", "features": blds},
            "boundary": {"type": "Feature", "properties": {}, "geometry": ring}}


def _ckey(g):  # build_context_colors.key_of 와 같은 키
    rp = g.representative_point()
    return f"{rp.x:.1f},{rp.y:.1f},{round(g.area)}"


def shapely_union(gs):
    from shapely.ops import unary_union
    return unary_union(gs)


def shapely_transform(g, fn):
    import numpy as np
    import shapely
    return shapely.transform(g, lambda c: np.column_stack(fn(c[:, 0], c[:, 1])))


def main():
    OUT.mkdir(exist_ok=True)
    parcels = json.load(open(ROOT / "data/parcels.geojson"))
    context = context_map({f["properties"]["pnu"] for f in parcels["features"]})
    for f in parcels["features"]:
        p = f["properties"]
        f["properties"] = {k: p.get(k) for k in ("jibun", "jimok", "side", "anchor", "area_m2", "surveyed_roadview", "sliver")}

    bg = json.load(open(ROOT / "data/buildings_current.geojson"))
    pgeom = {f["properties"]["jibun"]: (shape(f["geometry"]), f["properties"]["jimok"]) for f in parcels["features"]}
    feats, excluded = [], []
    for f in bg["features"]:
        p = f["properties"]
        h = float(p["height_m"] or 0)
        fl = int(p["floors_up"] or 0)
        yr = int(p["approved"][:4]) if p["approved"] else None
        if yr is None or (h == 0 and fl == 0) or p["bid"] in EXCLUDE_BIDS:
            excluded.append(p["bid"])
            continue
        flags = []
        basis = "대장·브이월드 높이"
        note = ""
        if p["bid"] in LANDMARK_START:  # 창천교회: 1906년 창설(사용자 제공). 현 건물은 대장상 1989 허가·착공, 1994 사용승인
            note = f"창천교회 1906년 창설(사용자 제공). 이 건물은 대장 기준 {yr}년 사용승인"
            flags.append("landmark_proxy")
            note += ". 항공사진상 1990년에 이미 지붕이 보여 공사 애니메이션 없이 처음부터 완공 모습으로 표시"
            yr = LANDMARK_START[p["bid"]]
        ph = phase(p["jibun"], p["approved"]) if p["approved"] and "landmark_proxy" not in flags else None
        if h == 0:
            h, basis = round(fl * 3.3, 1), "층수×3.3m 추정"
        if yr < 1990:
            flags.append("old_date")
        pp = {"a": ph[0], "b": ph[1], "a_s": ph[2], "b_s": ph[3], "pbasis": ph[4]} if ph else {}
        ms = massing(p["bid"], f["geometry"]["coordinates"][0]) if f["geometry"]["type"] == "Polygon" else None
        for k, (r2, b2, t2, c2) in enumerate(ms or []):
            feats.append({"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [r2]},
                          "properties": {"bid": p["bid"], "jibun": p["jibun"], "start": yr, "height": t2, "base": b2, "color": c2,
                                         "part": 1, "floors_up": fl, "floors_down": 0, "height_basis": "사진 기반 근사 형상",
                                         "flags": ";".join(flags), "start_note": "", **pp}})
        # 건물 바닥 면적 중 각 필지와 겹치는 비율(%). 5% 미만 조각은 도면 오차로 보고 버린다. 면적비는 아핀 변환에 불변이라 경위도 그대로 계산해도 된다.
        bgm = shape(f["geometry"]).buffer(0)
        spans = sorted(({"jibun": k, "jimok": v[1], "pct": round(bgm.intersection(v[0]).area / bgm.area * 100)}
                        for k, v in pgeom.items() if bgm.intersects(v[0])), key=lambda x: -x["pct"])
        spans = [x for x in spans if x["pct"] >= 5]
        feats.append({"type": "Feature", "geometry": f["geometry"],
                      "properties": {"bid": p["bid"], "jibun": p["jibun"], "start": yr, "height": h, "spans": spans,
                                     "floors_up": fl, "floors_down": int(p["floors_down"] or 0),
                                     "height_basis": basis, "flags": ";".join(flags), "start_note": note,
                                     "base": 0, "color": "", "part": 0, "hide": 1 if ms else 0, **pp}})
    buildings = {"type": "FeatureCollection", "features": feats}
    new_start = {}
    for f in feats:
        pr = f["properties"]
        if pr["part"] == 0 and pr.get("a") is not None:
            new_start[pr["jibun"]] = max(pr["a"], new_start.get(pr["jibun"], 0))  # 2-46은 대장상 2003 건물이 현 건물(B025 1994는 도면 날짜 오류 의심)
    ghost_fc, ghost_info = ghosts({k: v[0] for k, v in pgeom.items()}, new_start)

    biz = []
    for b in rc("data/timeline_businesses.csv"):
        biz.append({k: b[k] for k in ("jibun", "name", "license_type", "category", "floor", "start", "end", "end_basis",
                                      "grade", "flags", "sign_first", "sign_last", "start_after", "end_before",
                                      "web_state", "web_first", "web_last", "start_basis", "source", "sign_units", "observed_as", "sign_count")})
    bev = [{k: b[k] for k in ("jibun", "status", "start", "end", "end_basis", "structure", "use", "floors_up", "grade")}
           for b in rc("data/timeline_buildings.csv") if b["status"] != "현존"]
    # 건축물대장 층별개요(현존 건물): 층마다 용도·면적. 대장 작성 시점(crtnDay) 기준의 현재 상태이므로 과거 용도로 쓰지 않는다.
    floors = {}
    flr_raw = json.loads((ROOT / "data/raw/hub/br_flr.json").read_text(encoding="utf-8"))
    apr = {x["mgmBldrgstPk"]: x["useAprDay"] for rows in json.loads((ROOT / "data/raw/hub/br_title.json").read_text(encoding="utf-8")).values() for x in rows}
    for jb, rows in flr_raw.items():
        for x in rows:
            kind = {"지상": "", "지하": "B", "옥탑": "R"}.get(x["flrGbCdNm"].strip())
            if kind is None:
                continue
            key = "R" if kind == "R" else kind + str(x["flrNo"])
            d = str(apr.get(x["mgmBldrgstPk"]) or "")
            floors.setdefault(jb, []).append({
                "pk": x["mgmBldrgstPk"], "apr": f"{d[:4]}-{d[4:6]}-{d[6:8]}" if len(d) == 8 else "",
                "att": 1 if x["mainAtchGbCd"] == "1" else 0, "key": key, "label": x["flrNoNm"].strip(),
                "struct": x["strctCdNm"].strip(), "use": x["mainPurpsCdNm"].strip(), "etc": (x["etcPurps"] or "").strip(),
                "area": x["area"], "area_excl": x["areaExctYn"] == "1", "crtn": x["crtnDay"]})
    scene = {"floors": floors, "parcels": parcels, "buildings": buildings, "businesses": biz, "building_events": bev,
             "excluded_buildings": excluded, "ghosts": ghost_fc, "ghost_info": ghost_info, "context": context, "year_min": 1992, "year_max": 2026}
    txt = json.dumps(scene, ensure_ascii=False)
    (OUT / "scene.json").write_text(txt)
    (OUT / "scene.js").write_text("window.SCENE=" + txt + ";")  # file:// 에서도 열리도록 script 로 읽는다
    print("parcels", len(parcels["features"]), "buildings", len(feats), "excluded", excluded,
          "businesses", len(biz), "building_events", len(bev),
          "context_parcels", len(context["parcels"]["features"]), "context_buildings", len(context["buildings"]["features"]))


if __name__ == "__main__":
    main()
