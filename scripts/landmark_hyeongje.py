"""신촌 형제갈비 건물(창천동 31-26, 1992-09 사용승인, 대장 높이 19.8m) 정밀 매싱.

근거 사진: data/raw/landmark/연세로12길/로드뷰/ 의 형제갈비_남측·남서측(로드뷰)·남서측(3D)·북측·서측(사용자 제공).
브이월드 외곽선(11꼭짓점)의 변을 방위로 나눠 면마다 다른 외장을 입힌다. 좌표는 외곽선 첫 꼭짓점을 원점으로 한 미터(x 동, y 북).
  e0   : 북동향 짧은 면(3.7m) — 남동 모서리 곡면 발코니가 이어진다
  e1   : 남동 모서리 모따기 면(8.1m) — 3~6층 둥근 콘크리트 발코니 슬래브 + 세로 노란 간판(1972년 개업)
  e3   : 남쪽 정면(15.2m) — 1층 한옥 기와 처마·돌벽·나무 기둥, 2~6층 회색 석재 패널 + 큰 유리 띠 + 세로 유리 틈
  e4,e5: 서쪽 면 — 남쪽 끝은 유리 띠, 나머지는 콘크리트 + 작은 창
  e6   : 북쪽 뒷면(12.9m) — 유리 띠와 석재 띠가 번갈아, 3층 높이에 붉은 '유료 주차장' 현수막, 2층에 실외기 줄
  e7~e10: 동쪽 이웃 건물 쪽 면 — 콘크리트 + 작은 창
  1층 남동 모서리는 흰 타일 '독립문 설렁탕' 점포, 남서 모서리는 붉은 간판의 스터디 카페.
높이: 1층 4.4m + 2~6층 각 2.96m = 19.2m, 난간 19.8m(대장 19.8m), 옥탑 상자 22m 안팎.
"""
import math
from shapely.geometry import box as sbox

from landmark_dokssuri import Edge, loc, rings

CONC, CONC2, SEAM, TILE = "#a9a59d", "#9b978f", "#8c8881", "#b9b5ac"
GLASS, GLASS2, WIN, WINFR = "#41505f", "#566879", "#2f3a46", "#e9ebee"
STONE, WOOD, ROOFT, ROOFC = "#cfc9bb", "#7a4a2c", "#4b4f56", "#383b41"
WHITE, STORE, RED, YEL = "#f4f4f1", "#2d2f33", "#c8283a", "#e4b933"
SLAB, ROOF, PARA, BOX = "#8d8a84", "#c9cdd3", "#a8a49c", "#e9ebee"

FL = [0.0, 4.4] + [4.4 + 2.96 * i for i in range(1, 6)]   # 6개 층 경계
H_TOP = FL[-1]          # 19.36
H_PAR = H_TOP + 0.6


def fl(f):
    return FL[f - 1], FL[f]


def hyeongje(P):
    parts = []

    def add(g, b, t, c):
        if g is not None and not g.is_empty:
            parts.append((g, b, t, c))

    n = len(P.exterior.coords) - 1
    E = {i: Edge(P, i) for i in range(n)}
    # ---- 본체: 1층(어두운 점포) + 2~6층 석재 패널 + 난간 + 옥상
    add(P, 0, FL[1], STORE)
    add(P, FL[1], H_TOP, CONC)
    inner = P.buffer(-0.4)
    add(P.difference(inner), H_TOP, H_PAR, PARA)
    add(inner, H_TOP, H_TOP + 0.15, ROOF)
    ledge = P.buffer(0.1).difference(P)
    for z in FL[1:-1]:
        add(ledge, z - 0.1, z + 0.1, SEAM)

    # ---- 남쪽 정면 e3: t 는 동쪽 끝에서 서쪽으로. s = L - t (서쪽 끝에서의 거리)
    e = E[3]
    L = e.L
    for f in range(2, 7):
        z0, z1 = fl(f)
        add(e.rect(L * 0.24, L * 0.76, 0, 0.2), z0 + 0.55, z1 - 0.55, GLASS if f % 2 else GLASS2)   # 큰 유리 띠
        add(e.rect(L * 0.24, L * 0.76, 0, 0.12), z0 + 0.45, z0 + 0.55, WINFR)
        add(e.rect(L * 0.12, L * 0.21, 0, 0.12), z0 + 0.7, z1 - 0.7, GLASS2)                       # 동쪽 좁은 세로창
        add(e.rect(L * 0.80, L * 0.90, 0, 0.2), z0 + 0.1, z1 - 0.1, WIN)                             # 서쪽 세로 유리 틈(전층)
        add(e.rect(L * 0.93, L * 0.98, 0, 0.12), z0 + 0.8, z1 - 0.8, GLASS2)                        # 서쪽 끝 좁은 창
    add(e.rect(L * 0.82 - 0.0, L * 0.86, 0.0, 0.25), FL[1], H_TOP, WIN)                             # 유리 틈 골격 이음
    # 2층 정면 간판: 흰 바탕 + 붉은 '신촌 형제갈비'
    add(e.rect(L * 0.25, L * 0.75, 0, 0.45), 3.3 + 1.3, 5.9, WHITE)
    add(e.rect(L * 0.34, L * 0.74, 0.45, 0.55), 4.5, 5.6, RED)
    # 6층 위 간판(같은 구성)
    add(e.rect(L * 0.25, L * 0.70, 0, 0.45), FL[5] + 2.0, FL[5] + 2.7, WHITE)
    add(e.rect(L * 0.34, L * 0.70, 0.45, 0.55), FL[5] + 2.05, FL[5] + 2.65, RED)

    # ---- 1층 남쪽: 한옥 상점 — 돌벽 + 나무 기둥 + 기와 처마
    add(e.rect(0.0, L, 0, 0.3), 0, 3.0, STONE)
    n_c = 6
    for k in range(n_c + 1):
        t = k * L / n_c
        add(e.rect(t - 0.22, t + 0.22, 0, 0.8), 0, 3.5, WOOD)
    add(e.rect(0, L, 0, 1.9), 3.5, 3.9, ROOFT)                    # 처마 (기와)
    add(e.rect(0, L, 0.2, 1.3), 3.9, 4.3, ROOFC)
    add(e.rect(0, L, 0.3, 0.8), 4.3, 4.4, ROOFC)
    add(e.rect(0, 3.2, 0, 1.9), 3.5, 3.9, ROOFT)
    # 남서 모서리 스터디 카페 붉은 간판
    add(e.rect(L - 3.4, L, 0, 0.55), 3.0, 4.2, RED)
    add(E[4].rect(0, 3.0, 0, 0.55), 3.0, 4.2, RED)

    # ---- 남동 모따기 e1 + e0: 3~6층 둥근 발코니 슬래브
    for i in (1, 0):
        e = E[i]
        for f in range(2, 7):
            z0, z1 = fl(f)
            add(e.rect(0.1, e.L - 0.1, 0, 0.14), z0 + 0.3, z1 - 0.55, GLASS2 if f % 2 else GLASS)   # 발코니 뒤 유리
            if f >= 3:
                add(e.rect(0.2, e.L - 0.2, 0, 0.9), z0 - 0.2, z0 + 0.25, SLAB)                         # 슬래브 안쪽 단
                add(e.rect(0.55, e.L - 0.55, 0.9, 1.2), z0 - 0.2, z0 + 0.25, SLAB)                     # 바깥 둥근 단
                add(e.rect(0.2, e.L - 0.2, 0.7, 0.9), z0 + 0.25, z0 + 0.55, CONC2)                    # 난간 벽
    # 최상층 위 캔틸레버 지붕 슬래브(곡면 발코니 맨 위)
    add(E[1].rect(0.2, E[1].L - 0.2, 0, 1.3), H_TOP, H_TOP + 0.35, SLAB)
    # 세로 노란 간판 '형제갈비 1972년 개업'
    e = E[1]
    t0 = e.L * 0.36
    add(e.rect(t0, t0 + 0.95, 1.25, 1.55), 7.2, 15.2, YEL)
    add(e.rect(t0 + 0.12, t0 + 0.83, 1.55, 1.63), 8.5, 13.0, RED)
    # 모서리 아래쪽: 2층은 창 달린 콘크리트
    for i in (1, 0):
        e = E[i]
        add(e.rect(e.L * 0.2, e.L * 0.85, 0, 0.2), FL[1] + 0.6, FL[1] + 2.3, WINFR)
        add(e.rect(e.L * 0.25, e.L * 0.8, 0, 0.28), FL[1] + 0.75, FL[1] + 2.15, GLASS2)
    # 1층 모서리: 흰 타일 독립문 설렁탕
    for i in (1, 0):
        e = E[i]
        add(e.rect(0, e.L, 0, 0.35), 0, 3.3, WHITE)
        add(e.rect(0.6, e.L - 0.6, 0.35, 0.42), 0.6, 2.8, STORE)                                       # 점포 유리
        add(e.rect(0, e.L, 0, 0.55), 3.3, 4.4, WHITE)                                                  # 간판 띠
    add(E[1].rect(1.2, E[1].L - 1.2, 0.55, 0.62), 3.55, 4.15, "#2a2a2a")                               # '독립문 설렁탕' 글자 띠
    add(E[10].rect(0, 5.0, 0, 0.35), 0, 4.4, WHITE)
    add(E[10].rect(0, 5.0, 0, 0.5), 3.3, 4.4, WHITE)

    # ---- 서쪽 e4(남쪽 끝) 유리 띠, e5 콘크리트 + 작은 창
    e = E[4]
    for f in range(2, 7):
        z0, z1 = fl(f)
        add(e.rect(0.3, e.L - 0.3, 0, 0.18), z0 + 0.6, z1 - 0.6, GLASS if f % 2 else GLASS2)
    e = E[5]
    for f in range(2, 7):
        z0, z1 = fl(f)
        add(e.rect(0.3, 6.0, 0, 0.18), z0 + 0.6, z1 - 0.6, GLASS2 if f % 2 else GLASS)                  # 남쪽 끝 큰 유리
        t = 7.4
        while t < e.L - 1.0:
            add(e.rect(t - 0.55, t + 0.55, 0, 0.14), z0 + 0.8, z0 + 2.0, WINFR)
            add(e.rect(t - 0.42, t + 0.42, 0, 0.2), z0 + 0.92, z0 + 1.9, WIN)
            t += 2.3
    add(e.rect(0, e.L, 0, 0.1), FL[1], H_TOP, TILE)

    # ---- 북쪽 뒷면 e6: 유리 띠 + 석재 띠 + 붉은 현수막 + 실외기
    e = E[6]
    for f in range(2, 7):
        z0, z1 = fl(f)
        add(e.rect(0.7, e.L - 0.7, 0, 0.18), z0 + 0.5, z1 - 0.7, GLASS if f % 2 else GLASS2)
        add(e.rect(0.1, e.L - 0.1, 0, 0.1), z1 - 0.7, z1, TILE)
    add(e.rect(0.15, e.L - 0.15, 0, 0.35), 6.6, 8.9, RED)
    add(e.rect(0.7, 5.5, 0.35, 0.42), 7.3, 8.3, WHITE)
    for k in range(6):
        t = 0.6 + k * 1.95
        add(e.rect(t, t + 1.2, 0, 0.9), 4.7, 6.0, "#e7e9ec")

    # ---- 동쪽 이웃 쪽(e7~e10): 막힌 콘크리트 + 작은 창
    for i in (7, 8, 9, 10):
        e = E[i]
        if e.L < 2.0:
            continue
        add(e.rect(0, e.L, 0, 0.1), FL[1], H_TOP, TILE)
        for f in range(2, 7):
            z0, z1 = fl(f)
            k = 1
            while k * 2.6 < e.L - 0.8:
                t = k * 2.6
                add(e.rect(t - 0.5, t + 0.5, 0, 0.14), z0 + 0.8, z0 + 2.0, WINFR)
                add(e.rect(t - 0.38, t + 0.38, 0, 0.2), z0 + 0.92, z0 + 1.9, WIN)
                k += 1

    # ---- 옥상 구조물(3D 사진): 북서쪽 큰 흰 상자, 북동쪽 작은 상자, 동쪽 가장자리 계단·승강기 탑
    R = P.buffer(-0.7)
    sb = lambda x0, y0, x1, y1: sbox(x0 - 6.9, y0 + 35.0, x1 - 6.9, y1 + 35.0)   # 아래 좌표는 필지 기준(첫 꼭짓점 (6.9,-35.0) 이 원점)
    add(R.intersection(sb(-11.8, -20.5, -5.0, -13.0)), H_TOP + 0.15, H_TOP + 3.0, BOX)
    add(R.intersection(sb(-3.8, -19.5, 0.8, -14.5)), H_TOP + 0.15, H_TOP + 2.6, BOX)
    add(R.intersection(sb(0.5, -33.5, 4.2, -28.0)), H_TOP + 0.15, H_TOP + 3.4, BOX)
    add(R.intersection(sb(-9.0, -31.0, -6.0, -28.5)), H_TOP + 0.15, H_TOP + 1.4, "#b7bcc4")
    return parts


def build(geo_ring):
    o = geo_ring[0]
    P = loc(geo_ring, o)
    out = []
    for g, b, t, c in hyeongje(P):
        for r in rings(g, o):
            out.append((r, round(b, 2), round(t, 2), c))
    return out
