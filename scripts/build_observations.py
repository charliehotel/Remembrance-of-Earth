"""로드뷰 조사 CSV(가로형)를 long-form data/observations.csv 로 바꾼다.
헤더 1행=지번(병합 셀은 앞 값 유지), 2행=층/구획, 3행~=촬영 연·월 별 관찰값.
status: observed(상호 있음) / vacant(공실) / unknown(미확인·판독불가) / not_surveyed(미관찰·조사 범위 밖)
주의: 외부에서 보이는 간판만 근거다. 간판이 없거나 안 보이는 업소는 누락될 수 있으므로,
관찰 없음/미확인/공실은 "영업 없음"의 증거가 아니다(존재 증거로만 사용).
사용: .venv/bin/python -I scripts/build_observations.py"""
import csv, re
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
rows = list(csv.reader(open(ROOT/"docs/Remembrance_of_Earth_yeonsero12gil_all12.csv", encoding="utf-8-sig")))
h1, h2, data = rows[0], rows[1], rows[2:]
parcel, cols = "", []
for i in range(2, len(h1)):
    if h1[i].strip():
        parcel = re.sub(r"창천동\s*", "", h1[i]).strip()
    cols.append((i, parcel, h2[i].strip()))
def status(v):
    v = v.strip()
    if not v or v.startswith("미관찰"): return "not_surveyed"
    if re.search(r"공실|비어 있", v): return "vacant"
    if "미확인" in v and not re.search(r"[가-힣A-Za-z0-9]{2,}\s*[\(·]", v.split("미확인")[0]) and len(re.sub(r"[^가-힣A-Za-z]", "", v.split("미확인")[0])) <= 12:
        return "unknown"
    if re.search(r"잠정|추정|판독|의심", v): return "tentative"
    if "미확인" in v: return "partial"
    return "named"
out = []
for r in data:
    if not r or not r[0].strip().isdigit(): continue
    y = int(r[0]); m = int(r[1]) if r[1].strip().isdigit() else 0
    for i, p, unit in cols:
        v = r[i].strip() if i < len(r) else ""
        out.append({"date": f"{y}-{m:02d}" if m else f"{y}", "jibun": p, "unit": unit, "raw": v, "status": status(v),
                    "source": "로드뷰 직접 조사", "grade": "C", "evidence_scope": "외부 간판만(부재 증거 아님)"})
with open(ROOT/"data/observations.csv", "w", encoding="utf-8-sig", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(out[0])); w.writeheader(); w.writerows(out)
from collections import Counter
print(len(out), Counter(o["status"] for o in out))
print("dates", sorted({o["date"] for o in out}))
print("parcels", sorted({o["jibun"] for o in out}))
for o in out:
    if o["status"] == "unknown": pass
print(Counter(o["raw"] for o in out if o["status"]=="unknown").most_common(12))
