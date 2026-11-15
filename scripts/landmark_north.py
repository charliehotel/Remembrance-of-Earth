"""연세로12길 북쪽 변 핵심 필지 건물 정밀 매싱(export_web.massing 에서 호출).

근거 사진: data/raw/roadview/좌2_창천동 2-2/, 좌3_창천동 2-7/ 의 2025~2026년 로드뷰 캡처(사용자 제공).
좌표는 외곽선 첫 꼭짓점을 원점으로 한 미터(x 동, y 북). 변의 t 는 변 시작점에서 끝점 쪽으로 잰다.

B024 (창천동 2-2, 1993-12 사용승인 4층, 대장 12.6m)
  남쪽 정면 e1(12.3m, t=0 동쪽 끝→서쪽 끝):
    1층 서쪽 5.3m 는 청록 타일 + 흰 간판 '공복식당' + 붉은 문, 가운데 3.9m 는 어두운 계단 입구 위 주황 'JJ music studio' 간판,
    동쪽 2.1m 는 흰 외벽 '청년국수' 점포. 2층은 회색 마감에 큰 유리창 둘(서쪽)과 어두운 테라스(동쪽).
    3~4층은 암갈색 벽돌, 흰 받침이 있는 돌출 창 3개와 세로 유리 슬릿.
  나머지 면은 암갈색 벽돌 + 작은 창.
B124 (창천동 2-7, 1993-06 사용승인 5층, 대장 13.2m)
  남쪽 정면 e8(8.3m)+e0(9.5m) 은 이어진 17.8m 면(동쪽 끝에서 서쪽 끝으로 T). 흑회색 세로 이음 징크 패널 전면,
    1층은 유리 점포(서쪽 가스트로펍, 동쪽 큰 유리), 가운데 T 7.4~9.7 은 어두운 출입구 + 위층 흰 '대흥교회' 간판,
    2층 서쪽 큰 유리띠(T 10.3~17.4), 3층 동쪽 4칸 창(T 2.7~6.8), 4층 동쪽 작은 창.
  나머지 면도 징크 패널 + 작은 창.
층고는 사진 비례 추정.
"""
from landmark_dokssuri import Edge


def _wrap(parts):
    def add(g, b, t, c):
        if g is not None and not g.is_empty:
            parts.append((g, b, t, c))
    return add


# ===================== B024 =====================
BRK, BRK2, GREY, GREY2 = "#744f4c", "#664644", "#7b7f84", "#6c7075"
TILEG, WHITE, SIGNW, RED, ORG = "#1f5c52", "#e8e8e6", "#f1ece0", "#a8262b", "#e8a63a"
GL, GLD, SILL = "#5d6670", "#2f343b", "#efefec"


def b024(P):
    parts = []
    add = _wrap(parts)
    FL = [0.0, 4.0, 7.3, 10.0, 12.6]
    n = len(P.exterior.coords) - 1
    E = {i: Edge(P, i) for i in range(n)}
    add(P, 0, FL[1], GREY2)
    add(P, FL[1], FL[2], GREY)
    add(P, FL[2], FL[4], BRK)
    inner = P.buffer(-0.3)
    add(P.difference(inner), FL[4], FL[4] + 0.8, BRK2)
    add(inner, FL[4], FL[4] + 0.12, "#8a8d90")

    e = E[1]
    L = e.L
    # 1층: 동쪽 청년국수(흰 외벽), 가운데 계단 입구, 서쪽 공복식당(청록 타일)
    add(e.rect(0, 2.1, 0, 0.2), 0, FL[1], WHITE)
    add(e.rect(0.3, 2.0, 0.2, 0.3), 0.3, 3.1, GLD)                              # 유리 점포
    add(e.rect(2.1, 6.2, 0, 0.1), 0, FL[1], GLD)                                 # 어두운 계단 입구
    add(e.rect(2.1, 6.0, 0, 0.45), 2.9, 4.0, ORG)                                # 주황 JJ music studio 간판
    add(e.rect(6.2, L, 0, 0.18), 0, 3.8, TILEG)                                  # 청록 타일 외벽
    add(e.rect(6.6, 7.6, 0.18, 0.28), 0.4, 3.0, RED)                             # 붉은 문
    add(e.rect(8.6, 11.8, 0.18, 0.3), 2.3, 3.6, SIGNW)                           # 흰 간판 '공복식당'
    add(e.rect(7.8, 11.8, 0.18, 0.26), 0.5, 2.1, GLD)                            # 서쪽 점포 유리
    # 2층: 서쪽 큰 유리창 둘 + 동쪽 어두운 테라스
    add(e.rect(6.3, 8.9, 0, 0.15), 4.5, 6.8, GLD)
    add(e.rect(9.1, 12.2, 0, 0.15), 4.5, 6.8, GLD)
    add(e.rect(0.1, 2.5, 0, 0.1), 4.4, 7.0, GLD)
    # 3~4층 돌출 창(흰 받침) + 세로 유리 슬릿
    for t0, t1 in ((8.6, 11.2), (6.4, 7.5), (0.9, 3.1)):
        add(e.rect(t0, t1, 0, 0.55), 7.5, 7.75, SILL)
        add(e.rect(t0 + 0.1, t1 - 0.1, 0.05, 0.45), 7.75, 9.2, GL)
        add(e.rect(t0, t1, 0, 0.55), 9.2, 9.4, SILL)
    add(e.rect(4.3, 5.5, 0, 0.12), 7.4, 12.0, GLD)
    for t0, t1 in ((8.7, 11.1), (1.0, 3.0)):
        add(e.rect(t0, t1, 0, 0.5), 10.3, 10.55, SILL)
        add(e.rect(t0 + 0.1, t1 - 0.1, 0.05, 0.45), 10.55, 11.8, GL)

    # 나머지 면: 벽돌 + 작은 창
    for i in (0, 2, 3, 4, 5, 6):
        e = E[i]
        if e.L < 2.0:
            continue
        for f in (2, 3):
            z0 = FL[f - 1]
            k = 1
            while k * 2.4 < e.L - 0.5:
                add(e.rect(k * 2.4 - 0.45, k * 2.4 + 0.45, 0, 0.1), z0 + 0.9, z0 + 2.0, GL)
                k += 1
    return parts


# ===================== B124 =====================
ZN, ZN2, ZSEAM = "#3d4249", "#33373d", "#2b2e33"
WSIGN, GLASS_Z, CURT = "#eceff1", "#58626d", "#d8dadc"


def b124(P):
    parts = []
    add = _wrap(parts)
    FL = [0.0, 3.9, 6.2, 8.5, 10.9, 13.2]
    n = len(P.exterior.coords) - 1
    E = {i: Edge(P, i) for i in range(n)}
    add(P, 0, FL[1], ZN2)
    add(P, FL[1], FL[5], ZN)
    inner = P.buffer(-0.3)
    add(P.difference(inner), FL[5], FL[5] + 0.8, ZN2)
    add(inner, FL[5], FL[5] + 0.12, "#7f8286")
    # 전 면 징크 패널 세로 이음(0.65m 간격)
    for i in range(n):
        e = E[i]
        if e.L < 2.0:
            continue
        k = 1
        while k * 0.65 < e.L:
            add(e.rect(k * 0.65, k * 0.65 + 0.04, 0, 0.05), FL[1], FL[5], ZSEAM)
            k += 1

    # 남쪽 정면: e8(동 8.3m) + e0(서 9.5m). 전체 T = 동쪽 끝에서의 거리.
    def front(T0, T1, o0, o1, b, t, col):
        T0, T1 = max(T0, 0), min(T1, 17.8)
        if T0 >= 8.3:
            add(E[0].rect(T0 - 8.3, T1 - 8.3, o0, o1), b, t, col)
        elif T1 <= 8.3:
            add(E[8].rect(T0, T1, o0, o1), b, t, col)
        else:
            add(E[8].rect(T0, 8.3, o0, o1), b, t, col)
            add(E[0].rect(0, T1 - 8.3, o0, o1), b, t, col)

    front(0.4, 6.9, 0, 0.2, 0.2, 3.5, GLASS_Z)                    # 1층 동쪽 큰 유리 점포
    front(10.9, 17.5, 0, 0.2, 0.2, 3.5, GLASS_Z)                  # 1층 서쪽 유리(가스트로펍)
    front(7.4, 9.7, 0, 0.1, 0, 3.6, "#17191d")                    # 가운데 어두운 출입구(안쪽)
    front(0, 17.8, 0, 0.35, 3.5, 3.9, "#2a2d31")                  # 1층 처마 간판 띠
    front(7.2, 10.1, 0.1, 0.2, 6.4, 7.6, WSIGN)                   # 흰 '대흥교회' 간판
    front(10.3, 17.4, 0, 0.15, 4.4, 5.9, GLASS_Z)                 # 2층 서쪽 큰 유리띠
    front(10.3, 17.4, 0.15, 0.22, 4.4, 5.9, CURT)                 # 흰 커튼
    front(1.2, 6.8, 0, 0.12, 4.2, 6.2, "#2a2d33")                 # 2층 동쪽 어두운 네온 패널
    front(2.7, 6.8, 0, 0.15, 6.6, 8.2, GLASS_Z)                   # 3층 동쪽 4칸 창
    for T in (3.7, 4.7, 5.8):
        front(T, T + 0.1, 0.15, 0.2, 6.6, 8.2, "#222428")
    front(4.6, 6.6, 0, 0.15, 10.4, 12.4, GLASS_Z)                 # 4층 동쪽 작은 창

    # 나머지 면: 작은 창
    for i in (1, 2, 4, 5):
        e = E[i]
        for f in (2, 3, 4, 5):
            z0 = FL[f - 1]
            k = 1
            while k * 2.8 < e.L - 0.6:
                add(e.rect(k * 2.8 - 0.5, k * 2.8 + 0.5, 0, 0.12), z0 + 0.6, z0 + 1.6, GLASS_Z)
                k += 1
    return parts


MODELS = {"B024": b024, "B124": b124}


# ===================== B111 =====================
# B111 (창천동 2-46, 학림빌딩, 2003-04 사용승인 5층, 대장 17.65m) — 흰 페인트 벽돌의 'FROMHEARTS' 건물.
# 근거: data/raw/landmark/연세로12길/로드뷰/학림빌딩_남서측·서측_2026.png(로드뷰 캡처).
#   서쪽 긴 면 e3(11.7m, t=0 남쪽→북쪽): 1층 유리 점포 + 갈색 어닝, 2층 흰 난간 발코니와 다칸 유리문, 3층 나무 발코니, 맨 위층 검은 틀 창 줄
#   남쪽 짧은 면 e0·e2·e10: 폭 좁은 면에 세로로 긴 검은 틀 슬릿 창, 1층 유리 점포
#   옥상 난간 + 철제 난간, 흰 마감. 층고는 사진 비례 추정.
WH, WH2, BLK, GLW = "#ececea", "#dcdcd8", "#222428", "#6f7f8c"
AWN, WOODB, RAILW = "#5a4a40", "#c9a76a", "#f2f2f0"


def b111(P):
    parts = []
    add = _wrap(parts)
    FL = [0.0, 4.0, 7.6, 11.0, 14.2, 17.2]
    n = len(P.exterior.coords) - 1
    E = {i: Edge(P, i) for i in range(n)}
    add(P, 0, FL[1], WH2)
    add(P, FL[1], FL[5], WH)
    inner = P.buffer(-0.25)
    add(P.difference(inner), FL[5], 17.65, WH2)
    add(inner, FL[5], FL[5] + 0.1, "#9a9a96")

    # 서쪽 긴 면
    e = E[3]
    L = e.L
    add(e.rect(0.3, L - 0.3, 0, 0.1), 0.3, 3.4, GLW)                       # 1층 유리
    for k in range(5):
        add(e.rect(0.3 + k * 2.3, 0.4 + k * 2.3, 0.1, 0.16), 0.3, 3.4, BLK)
    add(e.rect(0.2, L - 0.4, 0, 1.0), 3.3, 3.75, AWN)                        # 갈색 어닝
    add(e.rect(0.3, L - 0.6, 0, 1.15), 3.95, 4.2, RAILW)                    # 2층 발코니 바닥
    add(e.rect(1.0, 10.8, 0.1, 0.2), 4.4, 7.2, GLW)                         # 2층 유리문
    for k in range(8):
        add(e.rect(1.0 + k * 1.3, 1.07 + k * 1.3, 0.2, 0.26), 4.4, 7.2, BLK)
    add(e.rect(0.3, L - 0.6, 1.08, 1.15), 4.2, 5.2, RAILW)                  # 난간
    add(e.rect(2.0, 5.2, 0, 1.2), 7.5, 7.75, WOODB)                         # 3층 나무 발코니
    add(e.rect(2.2, 5.0, 0.05, 0.15), 8.0, 10.2, GLW)
    for k in range(5):                                                      # 맨 위 검은 틀 창 줄
        add(e.rect(1.5 + k * 2.0, 2.7 + k * 2.0, 0, 0.18), 14.6, 16.2, BLK)
        add(e.rect(1.65 + k * 2.0, 2.55 + k * 2.0, 0.18, 0.22), 14.75, 16.05, GLW)
    # 남쪽 짧은 면: 1층 유리 + 세로 슬릿 창
    for i in (0, 2, 10):
        e2 = E[i]
        add(e2.rect(0.2, e2.L - 0.2, 0, 0.1), 0.3, 3.3, GLW)
        add(e2.rect(0.2, e2.L - 0.2, 0.1, 0.18), 3.3, 3.9, AWN)
    e0 = E[0]
    add(e0.rect(1.9, 2.7, 0, 0.15), 4.6, 15.4, BLK)
    add(e0.rect(2.05, 2.55, 0.15, 0.2), 4.8, 15.2, GLW)
    # 동쪽 면·북쪽 면: 작은 창
    for i in (9, 4, 6, 8):
        e3_ = E[i]
        if e3_.L < 2.0:
            continue
        for f in (2, 3, 4):
            z0 = FL[f - 1]
            k = 1
            while k * 2.8 < e3_.L - 0.5:
                add(e3_.rect(k * 2.8 - 0.4, k * 2.8 + 0.4, 0, 0.12), z0 + 1.0, z0 + 2.2, GLW)
                k += 1
    return parts


MODELS["B111"] = b111
