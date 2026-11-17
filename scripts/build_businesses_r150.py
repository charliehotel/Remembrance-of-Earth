"""150m 확장 필지(in_core=False)의 업소 시간표를 만든다. 서울시 인허가 4종(창천동 추출본)을 지번으로만 매칭한다(등급 A).
로드뷰 간판 관찰·웹 언급은 이 필지들에 없으므로 비워 둔다. 기존 data/timeline_businesses.csv 는 건드리지 않는다.

- 같은 지번·이름·인허가일 중복은 하나로 합친다.
- 끝: 폐업일자, 없으면 인허가취소일자. 둘 다 없으면 비워 둔다(영업 중이거나 신고 누락).
- stale_open 플래그: 2000년 이전 인허가인데 폐업 기록이 없는 경우. 간판 확인이 없으므로 '폐업신고 누락 의심'으로 표시만 한다.

출력: data/timeline_businesses_r150.csv (export_web.py 가 scene.json 의 businesses 에 합친다)
사용: .venv/bin/python -I scripts/build_businesses_r150.py
"""
import csv
from collections import Counter
from pathlib import Path

import sys
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from match_restaurants import SOURCES, date10, fix_name, parse_floor, parse_jibun  # noqa: E402

PARCELS = ROOT / "data/parcels_r150.csv"
OUT = ROOT / "data/timeline_businesses_r150.csv"
FIELDS = ["jibun", "name", "license_type", "category", "floor", "start", "start_basis", "end", "end_basis",
          "sign_first", "sign_last", "sign_count", "source", "grade", "start_after", "end_before", "sign_units",
          "observed_as", "flags", "web_state", "web_first", "web_last", "web_n", "web_overlap"]


def main():
    new = {r["jibun"] for r in csv.DictReader(PARCELS.open(encoding="utf-8-sig")) if r["in_core"] == "False"}
    seen, rows = set(), []
    for kind, v in SOURCES.items():
        path = ROOT / f"data/interim/{v}_changcheon.csv"
        if not path.exists():
            continue
        for r in csv.DictReader(path.open(encoding="utf-8-sig")):
            j = parse_jibun(r["지번주소"])
            if j not in new:
                continue
            start = date10(r["인허가일자"])
            name = fix_name(r["관리번호"], r["사업장명"])
            key = (j, name, start)
            if key in seen:
                continue
            seen.add(key)
            end = date10(r.get("폐업일자")) or date10(r.get("인허가취소일자"))
            flags = "stale_open" if (not end and start and start < "2000" and r["영업상태명"].startswith("영업")) else ""
            rows.append({
                "jibun": j, "name": name, "license_type": kind,
                "category": r.get("업태구분명") or kind,
                "floor": parse_floor(r["지번주소"] or r["도로명주소"]),
                "start": start, "start_basis": "인허가일",
                "end": end, "end_basis": "폐업일" if end else r["영업상태명"],
                "sign_first": "", "sign_last": "", "sign_count": 0, "source": f"서울시 {kind} 인허가(LOCALDATA)",
                "grade": "A", "start_after": "", "end_before": "", "sign_units": "", "observed_as": "",
                "flags": flags, "web_state": "", "web_first": "", "web_last": "", "web_n": "", "web_overlap": "",
            })
    rows.sort(key=lambda r: (r["jibun"], r["start"], r["name"]))
    with OUT.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f"업소 구간={len(rows)} 필지={len({r['jibun'] for r in rows})}/{len(new)} 종류={dict(Counter(r['license_type'] for r in rows))} "
          f"종료 없음={sum(not r['end'] for r in rows)} stale_open={sum(bool(r['flags']) for r in rows)}")


if __name__ == "__main__":
    main()
