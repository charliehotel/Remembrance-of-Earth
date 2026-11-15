"""3D 사진(비스듬한 사진)의 카메라를 추정한다: data/context_cam3d.json

1단계: 두 사진에서 눈으로 대응시킨 지붕(교회·금송빌딩·진성빌딩·삼각형 건물 등) 기준점 9개로 카메라(위치 3·방향 3·초점거리 1)를 맞춘다.
  교회 모서리만으로는 깊이 방향이 불안정해서, 서로 멀리 떨어진 지붕 중심점을 함께 써야 풀린다.
2단계: 1단계 해를 시작점으로, 위성사진에서 뽑은 건물별 지붕색(rc)이 3D 사진의 지붕 위치 색과 같아지도록 조금씩 다듬는다.
카메라 모델: 핀홀, 주점은 사진 중앙, 정사각 화소. 월드는 창천교회 원점 기준 m(X 동, Y 북, Z 위).
사용: .venv/bin/python -I scripts/calibrate_3d_cam.py
"""
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from shapely.geometry import Polygon

ROOT = Path(__file__).resolve().parent.parent
PHOTO = ROOT / "data/raw/satellite/3D사진_창천교회 일대_상호 표시.png"
OUT = ROOT / "data/context_cam3d.json"
KX, KY = 111320 * math.cos(math.radians(37.559)), 110540
SCALE = 4  # 비용 계산은 1/4 해상도 사진으로

# 교회 본당 모서리(X, Y, Z) → 사진 화소(원본 해상도). 눈으로 읽은 값이라 오차 ±10px 정도: 보조 조건
CHURCH = [((25.2, -7.5, 0), (1105, 352)), ((-16.1, -7.5, 0), (838, 355)),
          ((25.2, -7.5, 14), (1105, 212)), ((-16.1, -7.5, 14), (838, 213)),
          ((24.1, -22.0, 0), (1112, 410)),        # 교차로 흰 원
          ((-35, -38, 33.5), (645, 310)),        # 금송빌딩 지붕 중심(B4)
          ((38, -91, 19.6), (1228, 650)),        # 진성빌딩 지붕(B68)
          ((29, -60, 13.2), (1165, 520)),        # 초록 지붕 건물(B78)
          ((68, -70, 25.3), (1460, 530))]        # 삼각형 흰 건물(B3)
START = [22.2, -374.9, 330.9, 0.005, 0.876, -0.001, 3430.0]  # 기준점만으로 얻은 해


def axes(yaw, pitch, roll):
    fwd = np.array([math.sin(yaw) * math.cos(pitch), math.cos(yaw) * math.cos(pitch), -math.sin(pitch)])
    right0 = np.array([math.cos(yaw), -math.sin(yaw), 0.0])
    up0 = np.cross(right0, fwd)
    if up0[2] < 0:
        up0 = -up0
    cr, sr = math.cos(roll), math.sin(roll)
    return right0 * cr + up0 * sr, -right0 * sr + up0 * cr, fwd


def project(p, X, W, H):
    r, u, f = axes(p[3], p[4], p[5])
    v = X - p[0:3]
    zc = v @ f
    zc_safe = np.where(zc > 1, zc, np.nan)
    return np.column_stack([W / 2 + p[6] * (v @ r) / zc_safe, H / 2 - p[6] * (v @ u) / zc_safe]), zc


def load_buildings():
    sc = json.loads((ROOT / "web/scene.json").read_text())
    cols = sc["context"]["buildings"]["features"]
    o = sc["context"]["center"]
    out = []
    for f in cols:
        pr = f["properties"]
        ring = np.array([((x - o[0]) * KX, (y - o[1]) * KY) for x, y in f["geometry"]["coordinates"][0]])
        rc = pr.get("rc")
        rgb = None if rc is None else np.array([int(rc[i:i + 2], 16) for i in (1, 3, 5)], float)
        out.append({"ring": ring, "h": pr["height"], "rgb": rgb})
    return out


def label_image(p, blds, W, H, walls=False):
    """건물 지붕(과 벽)을 먼 것부터 그려 가림을 반영한 번호 이미지. 지붕 번호=2i+1, 벽 번호=2i+2(walls=True)."""
    img = Image.new("I", (W, H), 0)
    dr = ImageDraw.Draw(img)
    cam = p[0:3]
    order = sorted(range(len(blds)), key=lambda i: -np.hypot(*(blds[i]["ring"].mean(0) - cam[:2])))
    for i in order:
        b = blds[i]
        ring, h = b["ring"], b["h"]
        if walls:
            n = len(ring) - 1
            for k in range(n):
                a, c = ring[k], ring[k + 1]
                # 카메라를 향한 벽만(바깥 법선과 카메라 방향의 내적 > 0). 링 방향에 상관없이 면적 부호로 보정
                area = 0.5 * np.sum(ring[:-1, 0] * ring[1:, 1] - ring[1:, 0] * ring[:-1, 1])
                e = c - a
                nrm = np.array([e[1], -e[0]]) * (1 if area > 0 else -1)
                if nrm @ (cam[:2] - (a + c) / 2) <= 0 or np.hypot(*e) < 1.0:
                    continue
                # 벽 중앙부만: 폭 15~85%, 높이 20%~85% (가장자리 번짐·지붕선 오차 피함)
                t0, t1 = 0.15, 0.85
                pa, pc = a + (c - a) * t0, a + (c - a) * t1
                quad = np.array([[*pa, h * 0.2], [*pc, h * 0.2], [*pc, h * 0.85], [*pa, h * 0.85]])
                q, zc = project(p, quad, W, H)
                if np.isnan(q).any():
                    continue
                dr.polygon([tuple(x) for x in q], fill=2 * i + 2)
        q, zc = project(p, np.column_stack([ring, np.full(len(ring), h)]), W, H)
        if not np.isnan(q).any() and (q.max(0) > -1e5).all():
            dr.polygon([tuple(x) for x in q], fill=2 * i + 1)
    return np.asarray(img)


def main():
    big = Image.open(PHOTO).convert("RGB")
    BW, BH = big.size
    small = big.resize((BW // SCALE, BH // SCALE), Image.BILINEAR)
    W, H = small.size
    arr = np.asarray(small).astype(float)
    blds = [b for b in load_buildings()]
    have = [i for i, b in enumerate(blds) if b["rgb"] is not None]
    target = np.zeros((len(blds), 3))
    for i in have:
        target[i] = blds[i]["rgb"]

    def cost(p, detail=False):
        if not (500 < p[6] < 12000 and 0.2 < p[4] < 1.45 and p[2] > 15):
            return 1e9
        lab = label_image(np.array([*p[:6], p[6] / SCALE]), blds, W, H)  # 초점거리도 1/4
        roofs = lab[(lab % 2 == 1)]
        idx = (lab - 1) // 2
        m = (lab % 2 == 1)
        cnt = np.bincount(idx[m], minlength=len(blds))
        sums = np.stack([np.bincount(idx[m], weights=arr[..., c][m], minlength=len(blds)) for c in range(3)], 1)
        mean = sums / np.maximum(cnt, 1)[:, None]
        vis = [i for i in have if cnt[i] >= 6]
        if len(vis) < 20:
            return 1e9
        d = np.array([np.abs(mean[i] - target[i]).sum() / 3 for i in vis])
        d = np.minimum(d, 70)  # 극단값(가림·오매칭)의 영향 제한
        photo_term = d.mean() + 20.0 * (1 - len(vis) / len(have)) ** 2 * 3
        # 교회 모서리(보조)
        pc = project(np.array(p), np.array([c[0] for c in CHURCH], float), BW, BH)[0]
        gt = np.array([c[1] for c in CHURCH], float)
        ch = np.nanmean(np.hypot(*(pc - gt).T)) if not np.isnan(pc).any() else 500
        total = photo_term + 0.35 * min(ch, 500) + 40 * abs(p[5])
        return (total, photo_term, ch, len(vis)) if detail else total

    rng = np.random.default_rng(7)
    p = np.array(START)
    c = cost(p)
    print("start cost", round(c, 2), cost(p, True))
    steps = np.array([3.0, 5.0, 5.0, 0.004, 0.006, 0.003, 60.0])
    for rnd in range(80):
        improved = False
        for k in rng.permutation(7):
            for sgn in (1, -1):
                q = p.copy()
                q[k] += sgn * steps[k]
                cq = cost(q)
                if cq < c:
                    p, c, improved = q, cq, True
                    break
        if not improved:
            steps *= 0.6
            if steps[0] < 0.1:
                break
    best = (c, p)
    c, p = best
    tot, photo, ch, nvis = cost(p, True)
    print("BEST total", round(tot, 2), "photo", round(photo, 2), "church px", round(ch, 1), "visible", nvis)
    OUT.write_text(json.dumps({"params": [float(x) for x in p], "photo_size": [BW, BH],
                               "note": "X,Y,Z(m),yaw,pitch,roll(rad),focal(px of original); principal point = image center",
                               "cost": {"total": tot, "photo": photo, "church_px": ch, "visible": int(nvis)}}, indent=1))
    print("->", OUT.relative_to(ROOT))


if __name__ == "__main__":
    main()
