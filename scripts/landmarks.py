"""랜드마크 3D 형상(사진 기반 근사). fill-extrusion 은 각기둥만 되므로 층층이 쌓아 박공·첨탑·창을 흉내 낸다.
대장 외곽선(필지 폴리곤)의 첫 꼭짓점을 원점으로 한 미터 좌표에서 부위를 만들고, (좌표링, base, top, color) 목록을 낸다.
높이: 교회 본체·탑 몸체는 대장(29.1m)과 사진 비례를 따른 추정, 첨탑 끝(~39m)은 사진 추정이며 대장 값이 아니다."""
import math
from shapely.geometry import Polygon, Point, box as sbox

KX, KY = 111320 * math.cos(math.radians(37.559)), 110540
BR, BR2, ROOF, SPIRE, WHITE, GLASS = "#9a4d3a", "#8b4433", "#7f9a86", "#4f6f5c", "#e8e2d4", "#232c3a"


def _loc(ring, o):
    return Polygon([((x - o[0]) * KX, (y - o[1]) * KY) for x, y in ring])


def _rings(g, o):
    out = []
    for gg in (g.geoms if hasattr(g, "geoms") else [g]):
        if gg.is_empty or gg.area < 0.3 or gg.geom_type != "Polygon":
            continue
        out.append([[o[0] + x / KX, o[1] + y / KY] for x, y in gg.exterior.coords])
    return out


class Edge:
    """외곽선의 i번째 변을 따라 바깥으로 튀어나온 직사각 조각(창·간판·기둥·박공)을 만든다."""
    def __init__(self, P, i):
        pts = list(P.exterior.coords)[:-1]
        self.A, B = pts[i], pts[(i + 1) % len(pts)]
        dx, dy = B[0] - self.A[0], B[1] - self.A[1]
        self.L = math.hypot(dx, dy)
        self.u = (dx / self.L, dy / self.L)
        ccw = P.exterior.is_ccw
        self.n = (self.u[1], -self.u[0]) if ccw else (-self.u[1], self.u[0])

    def rect(self, t0, t1, o0, o1):
        c = [(t0, o0), (t1, o0), (t1, o1), (t0, o1)]
        return Polygon([(self.A[0] + self.u[0] * t + self.n[0] * o, self.A[1] + self.u[1] * t + self.n[1] * o) for t, o in c])


def spire(cx, cy, z0, hs, layers, col):
    out = []
    z = z0
    for dz, h in layers:
        out.append((sbox(cx - h, cy - h, cx + h, cy + h), z, z + dz, col))
        z += dz
    return out


def church(P):
    parts = []
    add = lambda g, b, t, c: parts.append((g, b, t, c))
    nave = P.intersection(sbox(4.5, -9, 70, 40))
    add(nave, 0, 17, BR)
    # 지붕: 완만한 녹청 지붕을 단계로
    for k, (inset, z) in enumerate([(0.7, 17.5), (2.2, 18.2), (4.5, 18.9), (7.0, 19.5)]):
        add(nave.buffer(-inset).intersection(sbox(6, -9, 70, 40)), 17 + k * 0.0 if k == 0 else [17.5, 18.2, 18.9][k - 1], z, ROOF)
    # 본당 옆벽: 창 9칸 + 버트레스 꼭대기 뾰족 장식
    for idx in (11, 5):
        e = Edge(P, idx)
        t = 9.0
        while t < e.L - 4:
            add(e.rect(t - 0.95, t + 0.95, 0, 0.2), 4.5, 13.2, WHITE)
            add(e.rect(t - 0.7, t + 0.7, 0, 0.3), 4.8, 12.8, GLASS)
            add(e.rect(t - 0.35, t + 0.35, 0, 0.3), 12.8, 14.4, GLASS)
            p = t + 1.9
            add(e.rect(p - 0.45, p + 0.45, -0.9, 0.1), 17, 19.3, WHITE)
            add(e.rect(p - 0.2, p + 0.2, -0.65, -0.15), 19.3, 20.4, WHITE)
            t += 3.8
    # 탑 두 개
    for (y0, y1, cy) in ((-9, 6.9, 3.3), (18.6, 40, 22.2)):
        body = P.intersection(sbox(-6, y0, 4.5, y1))
        cx = 1.9
        add(body, 0, 20, BR)
        add(body.buffer(-0.35), 20, 26.2, BR2)
        for dy in (-2.5, 0, 2.5):  # 탑 전면 뾰족창
            for (z0, z1) in ((7.5, 12.5), (14, 18.5)):
                add(sbox(-0.25, cy + dy - 0.5, 0.05, cy + dy + 0.5), z0, z1, WHITE)
                add(sbox(-0.35, cy + dy - 0.3, 0.05, cy + dy + 0.3), z0 + 0.3, z1 - 0.2, GLASS)
        add(sbox(-0.35, cy - 0.8, 0.05, cy + 0.8), 22, 25.5, GLASS)  # 종탑 소리창
        for dx, dy in ((-2.6, -2.6), (2.6, -2.6), (2.6, 2.6), (-2.6, 2.6)):  # 탑 모서리 뾰족 장식
            for k, (h, z) in enumerate([(0.55, 26.2), (0.4, 28.4), (0.22, 29.6)]):
                add(sbox(cx + dx - h, cy + dy - h, cx + dx + h, cy + dy + h), z, [28.4, 29.6, 30.5][k], WHITE)
        s = spire(cx, cy, 26.2, 0, [(1.8, 2.5), (2.0, 2.0), (2.2, 1.55), (2.2, 1.15), (2.2, 0.8), (2.2, 0.5), (2.2, 0.28)], SPIRE)
        for g, b, t, c in s:
            add(g.intersection(Polygon([(-9, -9), (9, -9), (9, 40), (-9, 40)])), b, t, c)
        add(sbox(cx - 0.12, cy - 0.12, cx + 0.12, cy + 0.12), 38.6, 41.2, WHITE)  # 십자가
        add(sbox(cx - 0.55, cy - 0.1, cx + 0.55, cy + 0.1), 40.0, 40.3, WHITE)
    # 중앙: 현관(흰 아치) + 박공벽 + 큰 창
    add(P.intersection(sbox(-6, 6.9, 0, 18.6)), 0, 5.2, "#ddd7c8")
    for k, yc in enumerate((8.3, 12.75, 17.2)):  # 현관 아치 3개(어두운 입구)
        add(sbox(-2.7, yc - 0.9, -1.2, yc + 0.9), 0.0, 3.4, "#3a3a3a") if False else None
    gw = P.intersection(sbox(0, 6.9, 4.5, 18.6))
    add(gw, 0, 21, BR)
    for y0, y1, z in ((8.0, 17.5, 22.7), (9.4, 16.1, 24.0), (10.8, 14.7, 25.2), (11.8, 13.7, 26.0)):  # 박공 꼭대기를 단계로
        add(sbox(0, y0, 1.6, y1), z - (1.3 if z > 22.7 else 1.7), z, BR)
    add(sbox(-0.2, 7.5, 0.1, 17.3), 5.2, 19.0, WHITE)                 # 흰 아치 테두리
    add(sbox(-0.3, 8.1, 0.1, 10.9), 5.4, 15.8, GLASS)                 # 큰 창 왼
    add(sbox(-0.3, 11.9, 0.1, 16.7), 5.4, 15.8, GLASS) if False else None
    add(sbox(-0.3, 11.5, 0.1, 14.1), 5.4, 15.8, GLASS)
    add(sbox(-0.3, 8.4, 0.1, 11.0), 5.4, 15.8, GLASS) if False else None
    add(sbox(-0.3, 10.0, 0.1, 12.0), 15.8, 17.4, GLASS) if False else None
    add(sbox(-0.3, 11.2, 0.1, 13.4), 17.0, 19.0, "#6a97b8")           # 장미창
    return parts


def outback(P):
    parts = []
    add = lambda g, b, t, c: parts.append((g, b, t, c))
    SID, SID2, RED, FR = "#dcc7a1", "#e6d4ac", "#a5503a", "#7a4b32"
    add(P.intersection(sbox(20, -9, 40, 14)), 0, 3.6, "#d8bf9a")          # 동쪽 끝 막힌 벽
    S = Edge(P, 7)
    for t in (1.5, 8.0, 14.5, 21.0):  # 필로티 기둥(노랑·검정 줄무늬 아래쪽)
        add(S.rect(t, t + 0.9, -1.0, 0.0), 1.2, 3.6, "#d4bc98")
        add(S.rect(t, t + 0.9, -1.0, 0.05), 0, 1.2, "#d8b030")
    add(P.buffer(-0.15), 3.6, 7.6, SID)                                       # 2층
    add(P.buffer(0.35), 7.6, 8.3, RED)                                        # 붉은 차양
    up = P.buffer(-0.7)
    add(up.difference(sbox(-9, 4.2, 40, 15)), 8.3, 10.4, SID2)               # 3층(앞쪽 낮음)
    add(up.intersection(sbox(-9, 4.2, 40, 15)), 8.3, 13.5, SID2)             # 뒤쪽 높은 벽체
    add(up.intersection(sbox(-9, 4.2, 40, 15)).buffer(-1.5), 13.5, 13.9, RED)
    for e, ts in ((7, (3.0, 6.8, 13.2, 17.0, 24.0)), (5, (2.5, 6.0, 9.3)), (3, (2.2, 5.6, 9.0, 12.4))):
        E = Edge(P, e)
        for t in ts:
            add(E.rect(t - 1.0, t + 1.0, 0, 0.15), 4.7, 6.5, FR)
            add(E.rect(t - 0.8, t + 0.8, 0, 0.25), 4.9, 6.3, "#9aa58a")
    for t in (10.0, 19.0):  # 박공(삼각) 단계 + 간판
        for hw, z0, z1 in ((3.0, 8.3, 9.1), (2.2, 9.1, 9.9), (1.4, 9.9, 10.7), (0.6, 10.7, 11.3)):
            add(S.rect(t - hw, t + hw, -0.9, 0.05), z0, z1, SID2)
        add(S.rect(t - 1.7, t + 1.7, -0.95, -0.7), 8.5, 9.4, "#7a1f2a")
    return parts


def massing(bid, ring):
    o = ring[0]
    P = _loc(ring, o)
    parts = {"B098": church, "B078": outback}.get(bid)
    if not parts:
        return None
    out = []
    for g, b, t, c in parts(P):
        if g is None:
            continue
        for r in _rings(g, o):
            out.append((r, b, t, c))
    return out
