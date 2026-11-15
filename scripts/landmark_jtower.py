"""신촌 J타워(창천동 31-92, 1990-12 사용승인 지상 10층·지하 2층, 브이월드 높이 44.8m) 정밀 매싱.

근거 사진: data/raw/landmark/연세로12길/로드뷰/ 의 J타워_남동측·남서측·동측(사용자 제공).
브이월드 '나동' 외곽선(18꼭짓점, 172㎡)의 변을 방위로 나눠 면마다 다른 외장을 입힌다. 좌표는 외곽선 첫 꼭짓점을 원점으로 한 미터(x 동, y 북).
  e8       : 동북동 긴 면(23.4m) — 남쪽 끝 4.8m 는 붉은 철골 프레임 + 층마다 가로살대가 있는 세로 유리 띠(사진 동측·남동측), 나머지는 갈색 벽돌
  e9~e17   : 남쪽 끝 지그재그 면 — 남남동향 변은 청록 곡면 유리 슬릿이 든 벽돌 기둥, 서남서향 변은 어두운 벽돌 + 층별 반원 발코니 구멍(사진 남서측 오른쪽)
  e0, e2   : 남서향 면(7.6m+8.3m) — 큼직한 갈색 패널 + 이음매 + 작은 네모 창, 면 왼쪽에 붉은 기둥이 서 있는 나선 비상계단(사진 남서측)
  e3~e7    : 북북서향 면 — 벽돌 + 좁은 틈 창
  1층      : 검은 화강석 + 목재 문, 남동 모서리·긴 면 남쪽 구간은 2층 높이의 흰 간판 띠(리가 플스방·무르다 헤어샵)와 필름 줄무늬 처마선
  옥상     : 남쪽 끝에 붉은 원통 캡과 난간(J 글자 위), 'J' 금색 글자는 프레임 위
높이: 1층 5.2m + 2~10층 각 4.0m = 41.2m, 난간 42.0m, 붉은 캡 꼭대기 44.8m(대장 44.8m). 층고는 사진 비례 추정.
"""
import math
from shapely.geometry import Point

from landmark_dokssuri import Edge, loc, rings

BRICK, BRICK2, BRICK3 = "#7b5c4d", "#6a4d40", "#8a6a58"
RED, REDD = "#b5252d", "#8f1c24"
GLASS_T, GLASS_D, WIN = "#6f9ba3", "#4d6574", "#2c353f"
PANEL, SEAM2, GRAN = "#a08674", "#8a7263", "#2a2c30"
SIGN, WOOD, GOLD = "#f2f2ee", "#6b3f2a", "#d9d2bd"
SPIRAL, DARKB, BLUE, YEL, RAIL = "#25272b", "#33363c", "#2d5aa6", "#e8b73a", "#d7d5cc"
ROOF, PARA = "#9a9a96", "#8a6a58"

FL = [0.0, 5.2] + [5.2 + 4.0 * i for i in range(1, 10)]   # 10개 층 경계
H_TOP = FL[-1]          # 41.2
H_PAR = H_TOP + 0.8
H_CAP = 43.6
H_MAX = 44.8


def fl(f):
    return FL[f - 1], FL[f]


def jtower(P):
    parts = []

    def add(g, b, t, c):
        if g is not None and not g.is_empty:
            parts.append((g, b, t, c))

    n = len(P.exterior.coords) - 1
    E = {i: Edge(P, i) for i in range(n)}
    # ---- 본체: 1층 검은 화강석 + 2~10층 벽돌 + 난간 + 옥상
    add(P, 0, FL[1], GRAN)
    add(P, FL[1], H_TOP, BRICK)
    inner = P.buffer(-0.35)
    add(P.difference(inner), H_TOP, H_PAR, PARA)
    add(inner, H_TOP, H_TOP + 0.15, ROOF)

    # ---- 동북동 긴 면 e8: t=0 북쪽 끝 → t=L 남쪽 끝
    e = E[8]
    L = e.L
    f0, f1 = L - 5.6, L - 0.8
    add(e.rect(f0, f1, 0, 0.4), 9.4, H_TOP, RED)                       # 붉은 프레임
    z = 10.0
    while z + 1.7 <= H_TOP - 0.5:
        add(e.rect(f0 + 0.4, f1 - 0.4, 0.4, 0.5), z, z + 1.7, GLASS_D if z < 20 else GLASS_T)   # 층마다 가로살대 사이 유리
        z += 2.0
    # 프레임 위 'J' 금색 글자
    jc = L - 3.2
    add(e.rect(jc - 0.1, jc + 0.35, 0.4, 0.6), H_TOP + 0.2, H_TOP + 2.4, GOLD)
    add(e.rect(jc - 0.7, jc + 0.35, 0.4, 0.6), H_TOP + 0.2, H_TOP + 0.65, GOLD)
    add(e.rect(jc - 0.7, jc - 0.3, 0.4, 0.6), H_TOP + 0.2, H_TOP + 1.0, GOLD)
    # 북쪽 벽돌 구간: 작은 틈 창(사진 동측 오른쪽 위)
    for zz in (FL[8] + 1.2, FL[9] + 1.0):
        add(e.rect(1.2, 2.0, 0, 0.18), zz, zz + 1.7, WIN)
    for k in range(3):
        add(e.rect(8.0 + k * 3.4, 8.6 + k * 3.4, 0, 0.1), FL[1] + 2.0, FL[1] + 3.3, BRICK2)   # 벽돌면 음영 줄무늬(세로)

    # ---- 1~2층 간판: 남쪽 끝(e9)·긴 면 남쪽 12m
    sign_t0 = L - 12.5
    add(e.rect(sign_t0, L, 0, 0.55), 5.2, 5.5, DARKB)                  # 필름 줄무늬 처마선
    add(e.rect(sign_t0, L, 0, 0.45), 5.5, 9.2, SIGN)
    add(e.rect(sign_t0, L, 0, 0.6), 9.2, 9.6, DARKB)
    add(e.rect(L - 12.0, L - 6.8, 0.45, 0.55), 6.0, 8.6, "#f6f1e4")     # 흰 바탕 '리가 플스방'
    add(e.rect(L - 11.4, L - 7.6, 0.55, 0.62), 6.4, 8.2, BLUE)
    add(e.rect(L - 7.0, L - 4.0, 0.45, 0.55), 6.0, 8.4, "#e5e1d6")
    add(e.rect(L - 6.4, L - 4.4, 0.55, 0.62), 6.8, 7.8, DARKB)          # '무르다 Hair shop'
    add(e.rect(L - 12.0, L - 11.3, 0.45, 0.6), 5.7, 9.0, YEL)
    # 1층 목재 문·유리
    add(e.rect(L - 12.5, L - 6.0, 0, 0.3), 0, 3.6, WOOD)
    for k in range(5):
        add(e.rect(L - 12.2 + k * 1.3, L - 11.4 + k * 1.3, 0.3, 0.4), 0.2, 3.3, "#4a2c1d")

    # ---- 남쪽 끝 지그재그 e9..e17
    for i in range(9, 18):
        e = E[i]
        brg = math.degrees(math.atan2(e.n[0], e.n[1])) % 360
        if brg < 200:      # 남남동향 변: 청록 곡면 유리 슬릿
            add(e.rect(0, e.L, 0, 0.12), 9.4, H_TOP - 0.3, BRICK3)
            if e.L > 1.0:
                c = e.L / 2   # 벽돌 기둥 한가운데 좁은 슬릿(사진 남동측 왼쪽 원통 기둥)
                add(e.rect(c - 0.45, c + 0.45, 0.12, 0.22), 9.8, H_TOP - 0.6, GLASS_T)
            if i == 9:
                add(e.rect(0, e.L, 0, 0.3), 5.2, 9.6, SIGN)
        else:               # 서남서향 변: 어두운 벽돌 + 반원 발코니 구멍
            add(e.rect(0, e.L, 0, 0.1), FL[1], H_TOP, BRICK2)
            for f in range(3, 11):
                z0, _ = fl(f)
                if e.L > 1.2:
                    add(e.rect(e.L * 0.2, e.L * 0.8, 0, 0.18), z0 + 1.2, z0 + 2.7, WIN)

    # ---- 남서향 면 e0, e2: 갈색 패널 + 이음매 + 작은 창
    for i in (0, 2):
        e = E[i]
        add(e.rect(0, e.L, 0, 0.1), FL[1], H_TOP, PANEL)
        k = 1
        while k * 1.6 < e.L:
            add(e.rect(k * 1.6, k * 1.6 + 0.07, 0.1, 0.16), FL[1], H_TOP, SEAM2)
            k += 1
        for z in FL[2:-1]:
            add(e.rect(0, e.L, 0.1, 0.16), z - 0.06, z + 0.06, SEAM2)
    e = E[2]
    for f in range(2, 11):
        z0, _ = fl(f)
        add(e.rect(e.L - 1.0, e.L - 0.5, 0.1, 0.22), z0 + 2.0, z0 + 2.5, WIN)     # 왼쪽 작은 네모 창 열
        add(e.rect(1.0, 1.6, 0.1, 0.22), z0 + 2.2, z0 + 2.7, WIN)
    # 나선 비상계단: 왼쪽 1/3 지점, 붉은 중심 기둥 + 층마다 어두운 디딤판 덩어리
    s0 = 2.4
    add(e.rect(s0, s0 + 1.4, 0, 0.5), FL[1], H_TOP - 1.0, SPIRAL)
    add(e.rect(s0 + 0.6, s0 + 0.8, 0.5, 0.7), FL[1], H_TOP - 0.5, RED)
    for f in range(2, 11):
        z0, _ = fl(f)
        off = 0.0 if f % 2 else 0.35
        add(e.rect(s0 - 0.1 + off, s0 + 1.3 + off, 0.5, 1.05), z0 - 0.1, z0 + 0.1, SPIRAL)
        add(e.rect(s0 - 0.1, s0 + 1.5, 0.5, 0.6), z0 + 0.1, z0 + 0.95, SPIRAL)
    # 남서향 면 1층: 검은 골함석 셔터(사진 남서측 오른쪽 아래)
    add(E[0].rect(0, E[0].L, 0, 0.15), 0.4, 4.6, "#3a3d44")

    # ---- 북북서향 e3~e7: 벽돌 + 좁은 틈 창
    for i in (3, 5, 7):
        e = E[i]
        add(e.rect(0, e.L, 0, 0.1), FL[1], H_TOP, BRICK2)
        if e.L > 3:
            for f in range(2, 11):
                z0, _ = fl(f)
                for k in (0.3, 0.6):
                    add(e.rect(e.L * k, e.L * k + 0.5, 0.1, 0.2), z0 + 1.6, z0 + 3.0, WIN)

    # ---- 옥상 붉은 원통 캡(남쪽 끝 프레임 위): 붉은 몸통 + 밝은 난간 고리
    e = E[8]
    t = e.L - 3.4
    cx = e.A[0] + e.u[0] * t - e.n[0] * 2.3
    cy = e.A[1] + e.u[1] * t - e.n[1] * 2.3
    cap = Point(cx, cy).buffer(3.4, 24).intersection(P.buffer(0.1))
    add(cap, H_PAR, H_CAP, RED)
    add(cap.difference(cap.buffer(-0.35)), H_CAP, H_MAX, RAIL)
    add(cap.buffer(-0.35), H_CAP, H_CAP + 0.1, REDD)
    return parts


def build(geo_ring):
    o = geo_ring[0]
    P = loc(geo_ring, o)
    out = []
    for g, b, t, c in jtower(P):
        for r in rings(g, o):
            out.append((r, round(b, 2), round(t, 2), c))
    return out
