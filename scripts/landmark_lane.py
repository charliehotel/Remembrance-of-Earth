"""백주년기념관·교회 북측 동서 뒷골목(남쪽 변에만 건물이 있다) 주변 건물 정밀 매싱. export_web._context_details 에서 호출.

근거 사진: data/raw/landmark/연세로12길/로드뷰/뒷골목_*.png (골목 로드뷰 캡처, 2026-07). 건물은 골목(북쪽)을 향한 북면이 정면이다.
정면 변은 북향(법선 방위 ±50° 안)인 가장 긴 변. 비율 f 는 서쪽 끝=0 → 동쪽 끝=1.

  stone (2-45 일대, 4층 13.9m): 회색 갈색 석재 패널. 북서 모서리에 유리 돌출 기둥(3~4층 'COFFEE' 간판), 북면은 큰 유리창 하나·검은 틀 작은 창 줄·3층 발코니, 1층은 검은 캐노피 아래 카페 유리
  brick (2-37, 뉴욕비앤씨 건물): 중간 갈색 벽돌 + 흰 틀 큰 창 + 짙은 갈색 돌 띠 + 1층 베이지 어닝
  red42 (2-42, 6층 18m): 이 골목에서 가장 밝은 적벽돌. 1층 석재 띠와 실외기, 위층 돌출 창 상자, 한쪽 가장자리 세로 유리 띠(사용자 제공 사진)
  dark38 (2-38 준스그릴, 5층): 아주 어두운 갈색 벽돌. 위층 돌출 창 상자, 세로 유리 띠, 1층 석재 띠 위 기와 차양
  gran39 (2-39 스스라멘, 5층 13.9m): 회색 석재 패널(이음 격자). 층마다 작은 창이 계단식으로 하나씩, 1층은 석재 기둥 사이 유리 점포
  hanok (2-77 댄싱홍콩, 1957 목구조 1층): 흰 회벽 + 돌 기단 + 나무 창틀 + 기와 처마 + 초록 목재 지붕, 동쪽 끝에 간판·나무 문 입구
  shop (2-78, 1985 벽돌 1층): 벽돌 + 초록 틀 유리 점포 + 체커 타일 기단 + 함석 차양
  rijeong (9-30 리정원다옴, 목구조 1층): 흰 회벽 + 검은 틀 큰 창 셋 + '利庭園' 흰 간판 띠 + 한쪽 끝 에어컨 실외기 줄 + 낮은 난간
  wood31 (9-31, 목구조 1층): 짙은 기와 처마·지붕 + 주황빛 나무 패널 점포(나무 틀 유리문) + 회색 시멘트 측벽
  사진: 큰길 모퉁이 로드뷰 캡처(2026-06) 두 건물이 나란히 있다.
  b089 (80-16 일심약국, 1996 승인 5층 18.15m, 핵심 필지 B089): 서쪽 도로(연세로)를 보는 서향 정면 e3. 베이지 타일 외벽 + 층마다 어두운 틀 창 둘 + 1층 파란 어닝·초록 '일심약국' 간판 + 흰 체크 '약' 기둥,
    북쪽 면에는 짙은 녹색 틀 돌출창 상자(로드뷰 2026-06·2024-08)
  pharm31 (31-2 가까운신촌약국, 4층 14.4m): 폭 좁은 흰 건물. 서향 정면 e3(5.6m): 1층 파란 어닝 + 붉은 십자 간판 띠 + 위층 흰 판에 붉은 '약' 세로 간판 둘(로드뷰 2026-06)
"""
import math

from landmark_dokssuri import Edge, loc, rings
from landmark_south import Bld, GLS, GLS2, GLD, FRM, RED

STONE, STONE2, SEAMS = "#8b7b72", "#7a6b63", "#6d5f58"
BRK, BRK2, BAND = "#7a4a44", "#6c403b", "#5a3a34"


def north_edge(P):
    best = None
    for i in range(len(P.exterior.coords) - 1):
        e = Edge(P, i)
        br = (math.degrees(math.atan2(e.n[0], e.n[1])) + 360) % 360
        if (br < 50 or br > 310) and e.L > 2.5 and (best is None or e.L > best[0]):
            best = (e.L, i)
    return best[1] if best else 0


def stone(P, H):
    fi = north_edge(P)
    b = Bld(P, fi, H, 4.2, 3, STONE, STONE2, west0=True)
    FL = b.FL
    b.fr(0.40, 1.0, 0, 1.6, 3.4, 3.8, "#26282c")                    # 1층 검은 캐노피
    b.fr(0.42, 0.99, 0, 0.16, 0.3, 3.3, GLD)                       # 카페 유리
    for k in range(6):
        b.fr(0.44 + k * 0.09, 0.45 + k * 0.09, 0.16, 0.24, 0.3, 3.3, "#15171a")
    b.fr(0.0, 0.36, 0, 0.3, 0.3, 3.0, "#6b5d56")                  # 서쪽 입구 쪽 석재
    b.fr(0.10, 0.28, 0, 0.12, 0.5, 2.6, GLD)
    # 북서 모서리 유리 돌출 기둥(3~4층)
    for f in (3, 4):
        z0 = FL[f - 1]
        b.fr(0.0, 0.2, 0, 0.8, z0 + 0.1, z0 + 0.35, STONE2)
        b.fr(0.01, 0.19, 0.05, 0.7, z0 + 0.35, z0 + 2.7, "#6f8ea0")
        b.fr(0.0, 0.2, 0, 0.8, z0 + 2.7, z0 + 2.9, STONE2)
    b.fr(0.0, 0.2, 0.2, 0.34, FL[2] + 0.3, FL[2] + 2.6, FRM)       # 'COFFEE' 세로 간판
    # 북면 위층: 큰 유리창 + 검은 틀 작은 창
    b.fr(0.62, 0.82, 0, 0.14, FL[1] + 0.7, FL[1] + 2.9, "#2a3036")
    b.fr(0.61, 0.83, 0, 0.1, FL[1] + 0.6, FL[1] + 3.0, "#15171a")
    for f in (2, 3, 4):
        z0 = FL[f - 1]
        for k in range(4):
            if f == 2 and k in (2, 3):
                continue
            b.fr(0.25 + k * 0.1, 0.30 + k * 0.1, 0, 0.14, z0 + 0.8, z0 + 2.0, "#15171a")
    b.fr(0.86, 0.98, 0, 1.0, FL[2] + 0.1, FL[2] + 0.3, "#3b3d42")  # 3층 발코니
    b.fr(0.86, 0.98, 0.95, 1.0, FL[2] + 0.3, FL[2] + 1.3, "#3b3d42")
    return b.parts


def brick(P, H):
    fi = north_edge(P)
    nf = max(3, int(round(H / 3.3)))
    b = Bld(P, fi, H, 3.6, nf - 1, BRK, BAND, west0=True, side_gl=FRM)
    FL = b.FL
    b.fr(0.0, 1.0, 0, 1.3, 3.0, 3.35, "#d8cfb4")                    # 베이지 어닝
    b.fr(0.05, 0.95, 0, 0.14, 0.3, 2.9, GLD)
    b.fr(0.0, 1.0, 0, 0.1, FL[1] - 0.6, FL[1] + 0.2, BAND)         # 짙은 갈색 돌 띠
    for f in range(2, len(FL)):
        z0 = FL[f - 1]
        for k in range(2):
            c = 0.25 + k * 0.5
            b.fr(c - 0.17, c + 0.17, 0, 0.12, z0 + 0.7, z0 + 2.1, FRM)       # 흰 창틀
            b.fr(c - 0.15, c + 0.15, 0.12, 0.18, z0 + 0.8, z0 + 2.0, "#5f8a96")   # 틴트 유리
    return b.parts


RED42, DARK38, GRAN = "#a8493b", "#4f352f", "#a7a9ad"
WIN_F, GLS_T = "#cdd2d5", "#6f9aa0"


def _bays(b, f0, f1, floors, z_off=0.3):
    for z in floors:
        b.bay(f0, f1, z + z_off)


def red42(P, H):
    fi = north_edge(P)
    b = Bld(P, fi, H, 3.6, 5, RED42, "#b5ad9f", west0=False, side_gl=GLS_T)
    FL = b.FL
    b.fr(0.0, 1.0, 0, 0.12, FL[1] - 0.5, FL[1] + 0.25, "#a79f91")           # 1층 석재 띠
    b.fr(0.05, 0.95, 0, 0.12, 0.3, 3.0, GLD)
    for k in range(4):
        b.fr(0.08 + k * 0.1, 0.16 + k * 0.1, 0, 0.5, 2.9, 3.4, "#e6e6e3")      # 2층 실외기 줄
    for f in (3, 4, 5):
        b.bay(0.12 + (f - 3) * 0.04, 0.46 + (f - 3) * 0.04, FL[f - 1] + 0.4)
    b.fr(0.74, 0.86, 0, 0.12, FL[1] + 0.5, H - 1.2, GLS_T)                    # 세로 유리 띠
    return b.parts


def dark38(P, H):
    fi = north_edge(P)
    nf = max(3, int(round(H / 3.3)))
    b = Bld(P, fi, H, 3.8, nf - 1, DARK38, "#8b8377", west0=False, side_gl=GLS_T)
    FL = b.FL
    b.fr(0.0, 1.0, 0, 0.12, FL[1] - 0.6, FL[1] + 0.2, "#8b8377")            # 석재 띠
    b.fr(0.0, 1.0, 0, 1.3, 3.3, 3.9, "#7a4638")                              # 기와 차양
    b.fr(0.05, 0.45, 0.2, 0.3, 2.4, 3.1, FRM)                                # 'Jun's Grill' 간판
    b.fr(0.45, 0.95, 0, 0.14, 0.3, 3.0, GLD)
    for f in range(2, len(FL)):
        b.bay(0.06 + (f % 2) * 0.05, 0.32 + (f % 2) * 0.05, FL[f - 1] + 0.5)
    b.fr(0.70, 0.80, 0, 0.12, FL[1] + 0.4, H - 1.0, GLS_T)
    return b.parts


def gran39(P, H):
    fi = north_edge(P)
    b = Bld(P, fi, H, 4.2, 3, GRAN, "#9a9c9e", west0=False, rim="#8d8f92")
    FL = b.FL
    fe = b.fe
    for k in range(1, 8):                                                      # 석재 패널 이음 격자
        b.fr(k / 8 - 0.004, k / 8 + 0.004, 0, 0.04, FL[1], H, "#8d8f92")
    for f in range(2, 5):
        b.fr(0.0, 1.0, 0, 0.04, FL[f - 1] - 0.03, FL[f - 1] + 0.03, "#8d8f92")
    b.fr(0.0, 1.0, 0, 0.35, FL[1] - 0.25, FL[1] + 0.05, "#9a9c9e")            # 1층 위 슬래브
    b.fr(0.04, 0.96, 0, 0.12, 0.3, 3.7, GLD)
    for k in (0.04, 0.5, 0.94):
        b.fr(k - 0.04, k + 0.04, 0, 0.3, 0, 4.0, "#9a9c9e")                    # 석재 기둥
    for f, (c0, c1) in zip((2, 3, 4), ((0.33, 0.58), (0.28, 0.50), (0.26, 0.43))):   # 사진: 층마다 하나씩 계단식으로
        z0 = FL[f - 1] + 0.9
        b.fr(c0 - 0.02, c1 + 0.02, 0, 0.3, z0 - 0.15, z0, "#c9cbcd")           # 튀어나온 창턱
        b.fr(c0, c1, 0, 0.1, z0, z0 + 1.4, "#5c6a74")
        b.fr(c0 - 0.01, c1 + 0.01, 0, 0.14, z0 + 1.4, z0 + 1.52, "#c9cbcd")
    return b.parts


TILE, WALLW, STONEB, WOOD, GRN = "#59504b", "#efece4", "#6e6e6c", "#7a4a2c", "#8fbba6"


def hanok(P, H):
    from shapely.geometry import box as _b
    parts = []

    def add(g, bz, tz, c):
        if g is not None and not g.is_empty:
            parts.append((g, bz, tz, c))

    n = len(P.exterior.coords) - 1
    E = {i: Edge(P, i) for i in range(n)}
    add(P, 0, 1.1, STONEB)                                                      # 돌 기단
    add(P, 1.1, 3.0, WALLW)                                                     # 회벽
    add(P.buffer(0.5), 3.0, 3.35, WOOD)                                         # 나무 처마 보
    add(P.buffer(0.5), 3.35, 3.7, TILE)                                         # 기와 처마
    add(P.buffer(-0.2), 3.7, 5.0, GRN)                                          # 초록 목재 지붕
    add(P.buffer(-1.6), 5.0, 5.9, GRN)                                          # 용마루 쪽
    # 북쪽 긴 벽(e6): 나무 창틀 작은 창 하나 + 큰 창 둘
    e = E[6]
    L = e.L
    for f0, f1 in ((0.04, 0.09), (0.22, 0.50), (0.55, 0.74)):
        add(e.rect(L * f0 - 0.1, L * f1 + 0.1, 0, 0.1), 1.0, 2.7, WOOD)
        add(e.rect(L * f0, L * f1, 0.1, 0.16), 1.15, 2.55, "#2d2a28")
    # 동쪽 끝(e7) 입구: 나무 문 + 간판 + 나무 기둥
    e = E[7]
    add(e.rect(0.3, 5.2, 0, 0.18), 0, 2.9, "#3a2a20")                          # 어두운 입구
    add(e.rect(0.1, 0.5, 0, 0.5), 0, 3.0, WOOD)                                  # 나무 기둥
    add(e.rect(4.6, 5.0, 0, 0.5), 0, 3.0, WOOD)
    add(e.rect(0.1, 5.0, 0.1, 0.55), 3.0, 4.3, "#2a2018")                        # 'DANCING HONG KONG' 간판 판
    add(e.rect(0.7, 4.4, 0.55, 0.62), 3.4, 4.0, "#d9b86a")
    add(e.rect(5.2, 9.0, 0, 0.12), 0.5, 2.9, WOOD)                               # 나무 문
    return parts


def shop(P, H):
    parts = []

    def add(g, bz, tz, c):
        if g is not None and not g.is_empty:
            parts.append((g, bz, tz, c))

    HH = 3.6
    n = len(P.exterior.coords) - 1
    E = {i: Edge(P, i) for i in range(n)}
    add(P, 0, HH, "#7a5648")                                                    # 벽돌
    add(P.difference(P.buffer(-0.25)), HH, HH + 0.5, "#6a4a3e")
    add(P.buffer(-0.25), HH, HH + 0.1, "#8d8e90")
    e = E[1]                                                                    # 북면 8.9m
    L = e.L
    add(e.rect(0.2, L - 0.2, 0, 0.12), 0.9, 3.2, "#2f5a46")                     # 초록 틀
    add(e.rect(0.45, L - 0.45, 0.12, 0.2), 1.0, 3.0, "#1f2428")                 # 유리
    k = 1
    while k < 6:
        add(e.rect(0.45 + k * (L - 0.9) / 6 - 0.04, 0.45 + k * (L - 0.9) / 6 + 0.04, 0.12, 0.26), 1.0, 3.0, "#2f5a46")
        k += 1
    for k in range(int(L / 0.45)):                                              # 체커 타일 기단
        add(e.rect(k * 0.45, k * 0.45 + 0.45, 0, 0.1), 0, 0.9, "#f2f2f0" if k % 2 else "#1d1d1f")
    add(e.rect(0, L, 0, 1.0), 3.2, 3.45, "#6d7075")                              # 함석 차양
    return parts


def rijeong(P, H):
    fi = north_edge(P)
    b = Bld(P, fi, 3.4, 3.4, 1, "#efede6", "#e4e1d8", west0=False, rim="#dcd9d0", side_gl="#2d3138")
    b.fr(0.08, 0.92, 0, 0.3, 2.45, 3.25, "#f7f6f1")                           # 흰 간판 띠
    for c in (0.18, 0.34, 0.50, 0.66, 0.78):
        b.fr(c - 0.03, c + 0.03, 0.3, 0.36, 2.6, 3.1, "#1c1c1e")              # 검은 한자 글씨('利庭園')
    for f0, f1 in ((0.14, 0.32), (0.38, 0.56), (0.62, 0.82)):
        b.fr(f0 - 0.01, f1 + 0.01, 0, 0.1, 0.8, 2.35, "#1f2124")              # 검은 창틀
        b.fr(f0, f1, 0.1, 0.16, 0.95, 2.2, "#4b5660")
    for k in range(3):
        b.fr(0.0 + k * 0.035, 0.032 + k * 0.035, 0, 0.5, 0.3, 2.2, "#d9dcdf")  # 실외기 줄
    return b.parts


def wood31(P, H):
    fi = north_edge(P)
    b = Bld(P, fi, 3.1, 3.1, 1, "#8a8a86", "#7c7c78", west0=False, rim="#7c7c78", side_gl="#2d3138")
    b.fr(0.0, 1.0, 0, 0.2, 0.0, 3.0, "#b0703f")                              # 주황빛 나무 패널
    b.fr(0.08, 0.92, 0.2, 0.28, 0.5, 2.7, "#2a3238")                         # 유리문
    for k in range(1, 8):
        b.fr(0.08 + k * 0.105 - 0.008, 0.08 + k * 0.105 + 0.008, 0.2, 0.34, 0.5, 2.7, "#7a4a2c")   # 나무 문살
    b.fr(0.08, 0.92, 0.2, 0.34, 0.45, 0.55, "#7a4a2c")
    b.fr(0.08, 0.92, 0.2, 0.34, 2.65, 2.75, "#7a4a2c")
    b.add(P.buffer(0.45), 3.1, 3.45, "#3d3532")                               # 기와 처마
    b.add(P.buffer(-0.1), 3.45, 4.2, "#4a3f3a")                               # 기와 지붕(맞배)
    b.add(P.buffer(-1.1), 4.2, 4.9, "#4a3f3a")
    b.add(P.buffer(-2.0), 4.9, 5.4, "#4a3f3a")
    return b.parts


GRNF, BEIGE = "#2f4a40", "#d9cdb8"


def b089(P, H=18.15):
    """80-16 일심약국 건물(export_web.massing 에서 호출). 정면은 서쪽 변 e3(9.3m)이고 서쪽 도로(연세로)를 향한다.
    비율 f 는 정면을 마주 봤을 때 왼쪽(북쪽 끝)=0 → 오른쪽(남쪽 끝)=1."""
    b = Bld(P, 3, H, 4.2, 4, BEIGE, "#c9bda6", west0=False, side_gl="#3a5a50")
    FL = b.FL
    b.fr(0.28, 0.92, 0, 0.9, 3.15, 3.45, "#2a4fa0")                              # 파란 어닝
    b.fr(0.28, 0.92, 0.1, 0.4, 3.45, 4.35, "#3fa24a")                            # 초록 간판 '일심약국'
    b.fr(0.40, 0.80, 0.4, 0.46, 3.7, 4.1, "#f2d94a")
    b.fr(0.28, 0.90, 0, 0.14, 0.3, 3.0, GLD)                                     # 1층 약국 유리
    b.fr(0.02, 0.26, 0, 0.14, 0.3, 3.0, "#2d3138")                               # 북쪽 점포
    b.fr(0.92, 0.99, 0, 0.35, 0.0, 6.0, "#efeff0")                               # 흰 체크 '약' 기둥
    for k in range(6):
        b.fr(0.925, 0.985, 0.35, 0.4, 0.4 + k * 0.9, 0.9 + k * 0.9, "#1f5a3a" if k % 2 else "#222")
    for f in (2, 3, 4, 5):                                                       # 층마다 어두운 틀 창 둘
        z = FL[f - 1] + 0.9
        for c0, c1 in ((0.18, 0.46), (0.54, 0.82)):
            b.fr(c0 - 0.012, c1 + 0.012, 0, 0.1, z, z + 1.6, "#26302e")
            b.fr(c0, c1, 0.1, 0.16, z + 0.1, z + 1.5, "#5b8a86")
    b.fr(0.0, 0.07, 0, 0.12, FL[1] + 0.3, H - 1.0, "#6f9a8a")                    # 모서리 세로 녹색 유리 띠
    # 북쪽 면(e4) 돌출창: 짙은 녹색 틀 상자(로드뷰 2024-08)
    e4 = b.E[4]
    for f in (2, 3, 4):
        z = FL[f - 1] + 0.6
        b.add(e4.rect(1.2, 3.6, 0, 0.7), z, z + 0.25, "#cfc6b4")
        b.add(e4.rect(1.3, 3.5, 0.05, 0.6), z + 0.25, z + 1.9, GRNF)
        b.add(e4.rect(1.5, 3.3, 0.1, 0.55), z + 0.4, z + 1.7, "#6f9a8a")
        b.add(e4.rect(1.2, 3.6, 0, 0.7), z + 1.9, z + 2.1, "#cfc6b4")
    return b.parts


def pharm31(P, H):
    """31-2 가까운신촌약국 건물: 폭 좁은 흰 건물. 정면은 서쪽(남서향) 변 e3(5.6m)."""
    b = Bld(P, 3, H, 4.0, 3, "#ecece9", "#e2e2de", west0=False, side_gl="#5f8a96")
    FL = b.FL
    b.fr(0.0, 1.0, 0, 0.9, 3.2, 3.5, "#2a4fa0")                                  # 파란 어닝
    b.fr(0.0, 1.0, 0, 0.25, 3.5, 4.3, "#f7f7f5")                                 # '가까운신촌약국' 간판 띠
    b.fr(0.05, 0.22, 0.25, 0.3, 3.6, 4.2, RED)                                   # 붉은 십자
    b.fr(0.05, 0.95, 0, 0.12, 0.3, 3.0, GLD)                                     # 유리 점포
    for z0, z1 in ((4.8, 7.4), (7.9, 10.5)):                                     # 붉은 '약' 세로 간판 둘
        b.fr(0.10, 0.90, 0.1, 0.5, z0, z1, "#f7f7f5")
        b.fr(0.2, 0.8, 0.5, 0.56, z0 + 0.3, z1 - 0.3, RED)
    return b.parts


class _M:
    def __init__(self, fn):
        self.fn = fn

    def build(self, geo_ring, H=None):
        o = geo_ring[0]
        P = loc(geo_ring, o)
        out = []
        for g, bz, tz, c in self.fn(P, H or 14.0):
            for r in rings(g, o):
                out.append((r, round(bz, 2), round(tz, 2), c))
        return out


STONE_M, BRICK_M = _M(stone), _M(brick)
RED42_M, DARK38_M, GRAN39_M = _M(red42), _M(dark38), _M(gran39)
HANOK_M, SHOP_M = _M(hanok), _M(shop)
RIJEONG_M, WOOD31_M = _M(rijeong), _M(wood31)
PHARM31_M = _M(pharm31)
