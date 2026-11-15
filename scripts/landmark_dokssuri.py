"""독수리빌딩(창천동 31-4 일대, 1998-09 사용승인 8층) 정밀 매싱.

근거 사진: data/raw/landmark/연세로12길/로드뷰/ 의 독수리빌딩_서측·남측·남동측, 독수리다방_북측(사용자가 4면에서 찍어 넣음).
브이월드 외곽선(15꼭짓점)의 변을 방위로 분류해 면마다 다른 외장을 입힌다. 좌표는 외곽선 첫 꼭짓점을 원점으로 한 미터(x 동, y 북).
  - NW·N 면(e2~e5): 곡면 유리 커튼월(사진 서측). 층마다 청회색 유리 띠 + 흰 스팬드럴 + 세로 멀리언
  - ESE 긴 면(e7)·E 면(e6): 회색 패널 외벽, 북쪽 끝에만 짝창 2열(사진 북측). 나머지는 이음매만 있는 막힌 패널
  - SW·W 면(e8~e14): 석재풍 패널 + 세로 짝창(사진 서측 왼쪽 날개)
  - 1층: 어두운 점포 유리 + 갈색 간판 띠(독수리약국), 2층 NW면 파란 현수막, 3층 '독수리다방' 간판
높이: 대장 지상 8층, 브이월드 33.5m. 1층 5.0m + 2~8층 각 3.6m = 30.2m, 난간 31.2m, 옥탑 33.5m (층고는 사진 비례 추정).
"""
import math
from shapely.geometry import Polygon, box as sbox

KX, KY = 111320 * math.cos(math.radians(37.559)), 110540

# 층 경계(m): 1층 5.0, 이후 3.6씩 8층 꼭대기 30.2
FL = [0.0, 5.0] + [5.0 + 3.6 * i for i in range(1, 8)]
H_TOP = FL[-1]           # 30.2
H_PAR = H_TOP + 1.0      # 난간 31.2
H_MAX = 33.5             # 옥탑 꼭대기(브이월드 높이)

def fl(f):
    """f층(2~8)의 (바닥, 천장) 높이"""
    return FL[f - 1], FL[f]


PANEL, PANEL2, STONE, SEAM = "#d3d8e0", "#c3c9d3", "#b9c0cb", "#aeb5c0"
GLASS, GLASS2, SPAN, MULL = "#6f8ea8", "#8ba9c0", "#e6e9ee", "#cfd6de"
WIN, WINFR = "#35495c", "#f2f3f5"
STORE, BROWN, BLUE, DARK = "#2a303a", "#5a4535", "#1d4fa2", "#1f2632"
ROOF, PARA, PENT = "#8fae9f", "#c9ccd3", "#dfe2e7"


class Edge:
    def __init__(self, P, i):
        pts = list(P.exterior.coords)[:-1]
        self.A, B = pts[i], pts[(i + 1) % len(pts)]
        dx, dy = B[0] - self.A[0], B[1] - self.A[1]
        self.L = math.hypot(dx, dy)
        self.u = (dx / self.L, dy / self.L)
        self.n = (self.u[1], -self.u[0]) if P.exterior.is_ccw else (-self.u[1], self.u[0])

    def rect(self, t0, t1, o0, o1):
        t0, t1 = max(t0, 0), min(t1, self.L)
        if t1 - t0 < 0.05:
            return None
        c = [(t0, o0), (t1, o0), (t1, o1), (t0, o1)]
        return Polygon([(self.A[0] + self.u[0] * t + self.n[0] * o, self.A[1] + self.u[1] * t + self.n[1] * o) for t, o in c])


def loc(ring, o):
    return Polygon([((x - o[0]) * KX, (y - o[1]) * KY) for x, y in ring])


def rings(g, o):
    out = []
    for gg in (g.geoms if hasattr(g, "geoms") else [g]):
        if gg.is_empty or gg.area < 0.02 or gg.geom_type != "Polygon":
            continue
        out.append([[round(o[0] + x / KX, 7), round(o[1] + y / KY, 7)] for x, y in gg.exterior.coords])
    return out


def dokssuri(P):
    parts = []

    def add(g, b, t, c):
        if g is not None and not g.is_empty:
            parts.append((g, b, t, c))

    E = {i: Edge(P, i) for i in range(len(P.exterior.coords) - 1)}
    # ---- 본체: 1층 점포(유리 박스) + 2~8층 패널 + 난간 + 옥상
    add(P, 0, FL[1], STORE)
    add(P, FL[1], H_TOP, PANEL)
    inner = P.buffer(-0.35)
    add(P.difference(inner), H_TOP, H_PAR, PARA)           # 난간 고리
    add(inner, H_TOP, H_TOP + 0.15, ROOF)                  # 옥상 바닥(연녹색 방수)
    # 층 구분 슬래브 띠(외벽에서 0.12m 돌출): 층마다 얇은 선이 보이게
    ledge = P.buffer(0.12).difference(P)
    for z in FL[1:-1]:
        add(ledge, z - 0.12, z + 0.12, SEAM)

    # ---- 면별 외장
    GL = (2, 3, 4, 5)              # NW·N 곡면 유리 면(3,4 는 꺾임 연결 짧은 변)
    for i in GL:
        e = E[i]
        for f in range(2, 9):
            z0, z1 = fl(f)
            add(e.rect(0.15, e.L - 0.15, 0, 0.28), z0 + 0.15, z1 - 1.0, GLASS if f % 2 else GLASS2)   # 유리 띠
            add(e.rect(0.1, e.L - 0.1, 0, 0.3), z1 - 1.0, z1 - 0.05, SPAN)                              # 스팬드럴
            n_m = max(int(e.L / 1.7), 1)
            for k in range(1, n_m):                                                                    # 세로 멀리언
                t = k * e.L / n_m
                add(e.rect(t - 0.05, t + 0.05, 0, 0.38), z0 + 0.15, z1 - 1.0, MULL)
    # 개폐창(유리 띠 아래쪽 흰 슬라이딩 창 한 쌍)
    for i in (2, 5):
        e = E[i]
        for f in (3, 5, 7, 8):
            z0 = fl(f)[0]
            for t in (e.L * 0.28, e.L * 0.72):
                add(e.rect(t - 0.9, t + 0.9, 0, 0.42), z0 + 0.5, z0 + 1.0, WINFR)

    # ESE 긴 면 e7(25.6m, 시작 = 북쪽 끝)과 E 면 e6: 패널 이음매 + 북쪽 짝창 2열
    e7, e6 = E[7], E[6]
    for e in (e7, e6):
        pitch = 1.6
        t = pitch
        while t < e.L - 0.2:                                                      # 세로 이음매
            add(e.rect(t - 0.03, t + 0.03, 0, 0.1), FL[1], H_TOP, SEAM)
            t += pitch
    for f in range(2, 9):
        z0, z1 = fl(f)
        for tc in (3.2, 7.6):                                                     # e7 북단 짝창 2열
            add(e7.rect(tc - 1.55, tc + 1.55, 0, 0.18), z0 + 0.7, z1 - 0.7, WINFR)
            add(e7.rect(tc - 1.35, tc + 1.35, 0, 0.26), z0 + 0.85, z1 - 0.85, WIN)
            add(e7.rect(tc - 0.04, tc + 0.04, 0, 0.3), z0 + 0.85, z1 - 0.85, WINFR)   # 창 가운데 문설주
        add(e6.rect(2.0, 4.6, 0, 0.18), z0 + 0.7, z1 - 0.7, WINFR)              # E 면 1열
        add(e6.rect(2.15, 4.45, 0, 0.26), z0 + 0.85, z1 - 0.85, WIN)

    # SW·W 날개(e8~e14): 석재풍 + 세로 짝창
    for i in (8, 9, 10, 11, 12, 13, 14):
        e = E[i]
        if e.L < 1.8:
            continue
        add(e.rect(0, e.L, 0, 0.12), FL[1], H_TOP, STONE)
        n_w = max(int(e.L / 3.0), 1)
        for f in range(2, 9):
            z0, z1 = fl(f)
            for k in range(n_w):
                tc = (k + 0.5) * e.L / n_w
                add(e.rect(tc - 0.65, tc + 0.65, 0, 0.2), z0 + 0.7, z1 - 0.6, WINFR)
                add(e.rect(tc - 0.5, tc + 0.5, 0, 0.28), z0 + 0.85, z1 - 0.75, WIN)

    # ---- 1층 점포: 갈색 간판 띠(독수리약국) + 2층 NW면 파란 현수막 + 기둥
    for i in (2, 3, 4, 5):
        e = E[i]
        add(e.rect(0, e.L, 0, 0.45), 4.1, 5.4, BROWN)                              # 간판 띠
        n_c = max(int(e.L / 3.4), 1)
        for k in range(1, n_c):                                                    # 점포 유리 사이 기둥
            t = k * e.L / n_c
            add(e.rect(t - 0.18, t + 0.18, 0, 0.3), 0.0, 4.1, PANEL2)
    add(E[2].rect(1.0, 9.8, 0, 0.5), 5.5, 8.5, BLUE)                               # 파란 현수막(NW 면 아래쪽)
    add(E[2].rect(1.4, 9.4, 0.5, 0.58), 6.2, 6.6, "#dfe8f5")                       # 현수막 글자 띠
    for e in (E[7], E[6]):
        add(e.rect(0, e.L, 0, 0.35), 4.1, 5.4, BROWN)                               # 동쪽 면 하단 간판 띠
    add(E[7].rect(0.0, 6.0, 0, 0.6), 0, 4.1, PANEL2)                               # 동쪽 입구 쪽 기둥벽(북 끝)
    # 코너 파란 '약' 박스: N 면 서쪽 끝(꺾임 e4 근처)
    add(E[4].rect(0, E[4].L, 0, 0.6), 1.5, 5.4, BLUE)
    add(E[5].rect(0, 1.8, 0, 0.6), 1.5, 5.4, BLUE)
    # 3층 '독수리다방' 간판(진한 현판 + 금색 글자 띠, NW 면 중앙)
    e = E[2]
    add(e.rect(8.6, 14.6, 0, 0.6), 11.3, 12.5, "#3a2e24")
    add(e.rect(9.2, 14.0, 0.6, 0.68), 11.65, 12.15, "#c9a65a")

    # ---- 옥상 구조물: 계단·승강기 옥탑 + 굴뚝형 설비(사진 남·남동 3D)
    pent = P.buffer(-1.0).intersection(sbox(15.5, 6.0, 25.5, 16.5))
    add(pent, H_TOP + 0.15, H_MAX - 0.15, PENT)
    add(pent.buffer(-0.3), H_MAX - 0.15, H_MAX, PARA)
    add(sbox(13.0, 2.5, 15.2, 5.0).intersection(P.buffer(-0.8)), H_TOP + 0.15, H_TOP + 2.0, "#a7aeb8")   # 설비 박스
    # 옥상 광고탑 틀(서측 사진 왼쪽 위): NW 모서리 위에 선 4개 + 얇은 상판
    e = E[2]
    for t in (0.8, 3.6):
        add(e.rect(t, t + 0.18, -0.1, 0.1), H_PAR, H_PAR + 2.0, "#4b5f78")
    add(e.rect(0.8, 3.8, -0.1, 0.1), H_PAR + 2.0, H_PAR + 2.2, "#4b5f78")
    return parts


def build(geo_ring):
    """geo_ring: 외곽선 경도·위도 링. [(링, base, top, color)] 를 낸다."""
    o = geo_ring[0]
    P = loc(geo_ring, o)
    out = []
    for g, b, t, c in dokssuri(P):
        for r in rings(g, o):
            out.append((r, round(b, 2), round(t, 2), c))
    return out
