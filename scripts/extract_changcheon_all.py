"""data/raw/서울시 <업종> 인허가 정보.csv 전체에서 창천동 레코드만 추출해 data/interim/<이름>_changcheon.csv 로 쓴다.
이미 추출본이 있는 업종은 건너뛴다(--redo 로 다시 추출). 새 업종은 match_restaurants.SOURCES 에 이름을 추가해야 매칭된다.
원본은 CP949(일부 깨진 바이트 → replace). 사용: .venv/bin/python -I scripts/extract_changcheon_all.py [--redo]
"""
import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from match_restaurants import SOURCES  # noqa: E402


def main():
    redo = "--redo" in sys.argv
    for src in sorted((ROOT / "data/raw").glob("서울시 * 인허가 정보.csv")):
        kind = re.fullmatch(r"서울시 (.+) 인허가 정보", src.stem).group(1)
        if kind not in SOURCES:
            print(f"건너뜀(SOURCES 에 없음): {kind}")
            continue
        dst = ROOT / f"data/interim/{SOURCES[kind]}_changcheon.csv"
        if dst.exists() and not redo:
            print(f"있음: {dst.name}")
            continue
        with src.open(encoding="cp949", errors="replace", newline="") as f:
            r = csv.DictReader(f)
            rows = [{k: (v or "").strip() for k, v in row.items()} for row in r
                    if "창천동" in (row.get("지번주소") or "") or "창천동" in (row.get("도로명주소") or "")]
            fields = r.fieldnames
        with dst.open("w", encoding="utf-8-sig", newline="") as g:
            w = csv.DictWriter(g, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)
        bad = sum(any("�" in v for v in row.values()) for row in rows)
        print(f"{kind}: 창천동 {len(rows)}건 (깨진 글자 포함 {bad}) → {dst.name}")


if __name__ == "__main__":
    main()
