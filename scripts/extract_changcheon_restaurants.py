"""서울시 일반음식점 인허가 CSV에서 서대문구 창천동 레코드만 추출한다.
사용: python -I scripts/extract_changcheon_restaurants.py <input.csv> <output.csv>
"""
import csv, sys
src, dst = sys.argv[1], sys.argv[2]
# 원본은 CP949이며 일부 깨진 바이트가 있어 replace로 읽는다(깨진 글자 수를 함께 보고).
enc = "cp949"
f = open(src, encoding=enc, errors="replace", newline="")
r = csv.DictReader(f)
rows = [ {k:(v or "").strip() for k,v in row.items()} for row in r
         if "창천동" in (row.get("지번주소") or "") or "창천동" in (row.get("도로명주소") or "") ]
with open(dst, "w", encoding="utf-8-sig", newline="") as g:
    w = csv.DictWriter(g, fieldnames=r.fieldnames); w.writeheader(); w.writerows(rows)
bad = sum(any("\ufffd" in v for v in row.values()) for row in rows)
print("encoding", enc, "rows", len(rows), "rows_with_replaced_chars", bad)
