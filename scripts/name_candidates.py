"""간판만 확인된 상호(review_queue_observations.csv)를 창천동 전체 인허가에서 이름으로 찾아
다른 지번으로 신고된 후보를 data/review_name_candidates.csv 로 낸다.
자동 확정하지 않는다(같은 이름의 다른 가게일 수 있음). 사람이 보고 ALIAS·PARCEL_GROUP에 반영한다.
사용: .venv/bin/python -I scripts/name_candidates.py"""
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from crosscheck import norm  # noqa: E402

FILES = ["restaurants", "rest_cafe", "karaoke", "beauty"]


def main():
    queue = list(csv.DictReader(open(ROOT / "data/review_queue_observations.csv", encoding="utf-8-sig")))
    lic = []
    for f in FILES:
        p = ROOT / f"data/interim/{f}_changcheon.csv"
        if p.exists():
            lic += list(csv.DictReader(open(p, encoding="utf-8-sig")))
    out = []
    for q in queue:
        n = q["key"]
        if len(n) < 3:
            continue  # '상호', '지하' 같은 짧은 잡음은 건너뛴다
        hits = [r for r in lic if n in norm(r["사업장명"])]
        if not hits or len(hits) > 5:
            continue  # 너무 흔한 이름(체인·일반명사)은 후보로 쓸모가 없다
        for r in hits:
            out.append({"jibun": q["jibun"], "observed_key": n, "observed_date": q["date"],
                        "license_name": r["사업장명"], "license_addr": r["지번주소"],
                        "licensed": r["인허가일자"][:10], "closed": r["폐업일자"][:10],
                        "decision": ""})
    with open(ROOT / "data/review_name_candidates.csv", "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)
    print("candidates", len(out))
    for o in out:
        print(o["jibun"], o["observed_key"], o["observed_date"], "->", o["license_name"], o["license_addr"], o["licensed"], o["closed"])


if __name__ == "__main__":
    main()
