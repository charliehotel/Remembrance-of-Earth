"""필지별 시간표를 만든다. 세 근거를 합친다.

1. 건물 이벤트(건축HUB, 등급 A): 표제부(현존 건물 허가·사용승인), 폐쇄말소대장(말소),
   철거멸실관리대장(철거), 인허가 기본개요(신축·증축·대수선·용도변경)
2. 업소 인허가(서울시 LOCALDATA, 등급 A): 인허가일~폐업일
3. 로드뷰 간판 관찰(직접 조사, 등급 C): 존재 증거로만 쓴다. 관찰이 없다고 영업이 없었다고 보지 않는다.

출력
- data/timeline_buildings.csv : 필지별 건물 존속 구간(현존 + 말소·철거된 건물)
- data/timeline_businesses.csv : 업소 존속 구간. 인허가 구간에 로드뷰 관찰을 붙이고,
  인허가가 없는 관찰 상호는 로드뷰만으로 구간(첫·마지막 관찰)을 만든다.
- data/timeline_events.csv : 위 모든 것을 날짜순 이벤트로 편 것(지도 타임엔진 입력용)

플래그(flags 열, ;로 구분)
- stale_open: 2000년 이전 인허가인데 '영업' 상태이고 최근 간판도 없음 → 폐업신고 누락 의심
- spans_rebuild: 영업 구간 안에서 그 필지 건물이 말소·철거·신축됨(일부말소 제외) → 실제로는 그때 끊겼을 가능성
- seen_after_close: 폐업일 이후에도 간판이 관찰됨(간판 잔존 또는 재개업)
- sign_only: 인허가 기록 없이 간판으로만 확인(인허가 대상 아닌 업종이거나 표기 차이)

사용: .venv/bin/python -I scripts/build_timeline.py
"""
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from crosscheck import PARCEL_GROUP, match, names  # noqa: E402

HUB = ROOT / "data/raw/hub"


def d(s):
    """YYYYMMDD → YYYY-MM-DD, 빈 값은 ''."""
    s = (s or "").strip()
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}" if len(s) == 8 and s.isdigit() else ""


def obs_key(date):
    """로드뷰 날짜(YYYY-MM 또는 YYYY)를 비교용 YYYY-MM-DD로. 월 미상은 연 중간(07-01)으로 둔다."""
    return f"{date}-15" if len(date) == 7 else f"{date}-07-01"


def load(name):
    return json.loads((HUB / f"{name}.json").read_text())


def read_csv(path):
    with open(path, encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def write_csv(path, rows):
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def buildings():
    rows, events = [], []
    for jibun, recs in load("br_title").items():
        for r in recs or []:
            rows.append({
                "jibun": jibun, "status": "현존", "kind": r["mainAtchGbCdNm"],
                "name": r["dongNm"].strip() or r["bldNm"].strip(),
                "start": d(r["useAprDay"]), "start_basis": "사용승인", "permit": d(r["pmsDay"]),
                "end": "", "end_basis": "",
                "floors_up": r["grndFlrCnt"], "floors_down": r["ugrndFlrCnt"], "height_m": r["heit"],
                "structure": r["strctCdNm"], "use": r["mainPurpsCdNm"] or r["etcPurps"],
                "total_area_m2": r["totArea"], "source": "건축물대장 표제부", "grade": "A",
            })
    for jibun, recs in load("sr_title").items():
        for r in recs or []:
            rows.append({
                "jibun": jibun, "status": r["shterGbCdNm"], "kind": r["mainAtchGbCdNm"],
                "name": r["dongNm"].strip() or r["bldNm"].strip(),
                "start": d(r["useAprDay"]), "start_basis": "사용승인" if d(r["useAprDay"]) else "미상",
                "permit": d(r["pmsDay"]),
                "end": d(r["shterDay"]), "end_basis": r["shterGbCdNm"],
                "floors_up": r["grndFlrCnt"], "floors_down": r["ugrndFlrCnt"], "height_m": r["heit"] or "",
                "structure": r["strctCdNm"], "use": r["mainPurpsCdNm"].strip() or r["etcPurps"],
                "total_area_m2": r["totArea"], "source": "폐쇄말소대장 표제부", "grade": "A",
            })
    for jibun, recs in load("ap_demol").items():
        for r in recs or []:
            end = d(r["demolEndDay"]) or d(r["demolExtngDay"]) or d(r["demolStrtDay"])
            rows.append({
                "jibun": jibun, "status": r["demolExtngGbCdNm"], "kind": "", "name": "",
                "start": "", "start_basis": "미상", "permit": "",
                "end": end, "end_basis": r["demolExtngGbCdNm"] if end else f"{r['demolExtngGbCdNm']}(날짜 없음)",
                "floors_up": "", "floors_down": "", "height_m": "",
                "structure": r["strctCdNm"].strip(), "use": r["mainPurpsCdNm"].strip(),
                "total_area_m2": r["totArea"], "source": "철거멸실관리대장", "grade": "A",
            })
    for jibun, recs in load("ap_basis").items():
        for r in recs or []:
            kind = r["archGbCdNm"].strip()
            if not kind:
                continue  # 구분 없는 행은 같은 허가의 부속 레코드(면적 0)
            for date, what in ((d(r["archPmsDay"]), "허가"), (d(r["realStcnsDay"]), "착공"),
                               (d(r["useAprDay"]), "사용승인")):
                if date:
                    events.append({"date": date, "jibun": jibun, "type": "building",
                                   "event": f"{kind} {what}", "subject": r["mainPurpsCdNm"].strip(),
                                   "detail": f"연면적 {r['totArea']}㎡", "source": "건축인허가 기본개요", "grade": "A"})
    for b in rows:
        detail = f"{b['structure']} {b['floors_up']}층 {b['use']}".strip()
        if b["start"]:
            events.append({"date": b["start"], "jibun": b["jibun"], "type": "building", "event": "건물 사용승인",
                           "subject": b["name"], "detail": detail, "source": b["source"], "grade": "A"})
        if b["end"]:
            events.append({"date": b["end"], "jibun": b["jibun"], "type": "building", "event": f"건물 {b['end_basis']}",
                           "subject": b["name"], "detail": detail, "source": b["source"], "grade": "A"})
    return rows, events


def businesses(rebuilds):
    lic = read_csv(ROOT / "data/business_records.csv")
    obs = [o for o in read_csv(ROOT / "data/observations.csv") if o["status"] in ("named", "tentative", "partial")]
    surveys = defaultdict(list)  # 필지별 실제 조사 날짜(미관찰 제외)
    for o in read_csv(ROOT / "data/observations.csv"):
        if o["status"] != "not_surveyed" and o["date"] not in surveys[o["jibun"]]:
            surveys[o["jibun"]].append(o["date"])

    # 같은 업소 인허가 중복(같은 지번·이름·인허가일) 제거
    seen, spans = set(), []
    for r in lic:
        k = (r["jibun"], r["name"], r["licensed"])
        if k in seen:
            continue
        seen.add(k)
        spans.append({"jibun": r["jibun"], "name": r["name"], "license_type": r["license_type"],
                      "category": r["category"], "floor": r["floor"],
                      "start": r["licensed"], "start_basis": "인허가일",
                      "end": r["closed"], "end_basis": "폐업일" if r["closed"] else r["status"],
                      "sign_first": "", "sign_last": "", "sign_count": 0, "sign_units": set(),
                      "observed_as": set(), "source": r["source"], "grade": "A", "flags": []})

    by_jibun = defaultdict(list)
    for s in spans:
        by_jibun[s["jibun"]].append(s)
    sign_only = {}
    for o in obs:
        for n in names(o["raw"]):
            cand = [s for j in [o["jibun"], *PARCEL_GROUP.get(o["jibun"], [])] for s in by_jibun[j] if match(n, [{"name": s["name"]}])]
            # 같은 이름이 여러 번 인허가됐으면 관찰 날짜를 포함하거나 가장 가까운 구간에 붙인다
            when = obs_key(o["date"])
            cand.sort(key=lambda s: (not (s["start"] <= when <= (s["end"] or "9999")),
                                     abs(int(when[:4]) - int((s["start"] or when)[:4]))))
            if cand:
                s = cand[0]
            else:
                s = sign_only.setdefault((o["jibun"], n), {
                    "jibun": o["jibun"], "name": n, "license_type": "", "category": "", "floor": "",
                    "start": "", "start_basis": "첫 간판 관찰", "end": "", "end_basis": "마지막 간판 관찰",
                    "sign_first": "", "sign_last": "", "sign_count": 0, "sign_units": set(),
                    "observed_as": set(), "source": "로드뷰 직접 조사", "grade": "C", "flags": ["sign_only"]})
            s["sign_count"] += 1
            s["sign_units"].add(o["unit"])
            s["observed_as"].add(o["raw"])
            if not s["sign_first"] or obs_key(o["date"]) < obs_key(s["sign_first"]):
                s["sign_first"] = o["date"]
            if not s["sign_last"] or obs_key(o["date"]) > obs_key(s["sign_last"]):
                s["sign_last"] = o["date"]

    out = []
    for s in spans + list(sign_only.values()):
        if s["grade"] == "C":
            # 로드뷰만으로 구간: 첫·마지막 관찰. 앞뒤 조사일은 경계 범위(이 사이 어딘가에서 시작·종료)
            ds = sorted(surveys[s["jibun"]], key=obs_key)
            i, j = ds.index(s["sign_first"]), ds.index(s["sign_last"])
            s["start"], s["end"] = s["sign_first"], s["sign_last"]
            s["start_after"] = ds[i - 1] if i > 0 else ""
            s["end_before"] = ds[j + 1] if j + 1 < len(ds) else ""
        else:
            s["start_after"] = s["end_before"] = ""
            # 최근(2024~) 간판이 보이면 실제 영업 중이므로 제외
            if s["end_basis"].startswith("영업") and s["start"] < "2000" and not s["sign_last"] >= "2024":
                s["flags"].append("stale_open")
            if s["end"] and s["sign_last"] and obs_key(s["sign_last"]) > s["end"]:
                s["flags"].append("seen_after_close")
        end = s["end"] if s["grade"] == "C" else (s["end"] or "9999")
        hits = [e for e in rebuilds.get(s["jibun"], []) if s["start"] and s["start"] < e[0] < (obs_key(end) if s["grade"] == "C" else end)]
        if hits:
            s["flags"].append("spans_rebuild:" + ",".join(f"{e[0]} {e[1]}" for e in hits))
        out.append({**{k: v for k, v in s.items() if k not in ("sign_units", "observed_as", "flags")},
                    "sign_units": "|".join(sorted(s["sign_units"])),
                    "observed_as": " | ".join(sorted(s["observed_as"]))[:300],
                    "flags": ";".join(s["flags"])})
    out.sort(key=lambda s: (s["jibun"], s["start"][:4] if s["start"] else "0", s["name"]))
    return out


def main():
    brows, events = buildings()
    # 필지 건물이 끊긴 시점: 말소·철거 날짜, 그리고 현존 건물 신축(허가일 기준. 1990년대 건물은 기본개요가 없다)
    rebuilds = defaultdict(list)
    for b in brows:
        # 일부말소는 부속 옛 건물(예: 2-2 목조주택)만 없어진 것이라 본 건물 영업을 끊지 않는다
        if b["end"] and b["end_basis"] != "일부말소" and (b["end"], b["end_basis"]) not in rebuilds[b["jibun"]]:
            rebuilds[b["jibun"]].append((b["end"], b["end_basis"]))
        if b["status"] == "현존" and b["kind"] == "주건축물" and b["permit"]:
            rebuilds[b["jibun"]].append((b["permit"], "현 건물 허가"))
    for v in rebuilds.values():
        v.sort()
    biz = businesses(rebuilds)
    # 웹 언급 요약(web_summary.py). 글 작성일이며 영업 시기가 아니다. 등급은 바꾸지 않고 보조 근거 열만 붙인다.
    wp = ROOT / "data/web_mentions_summary.csv"
    web = {(w["jibun"], w["name"]): w for w in read_csv(wp)} if wp.exists() else {}
    for s in biz:
        w = web.get((s["jibun"], s["name"])) if s["grade"] == "C" else None
        for c in ("web_state", "web_first", "web_last", "web_n", "web_overlap"):
            s[c] = ""
        if w:
            s.update(web_state=w["web_state"], web_first=w["web_first"], web_last=w["web_last"],
                     web_n=w["web_n"], web_overlap=w["overlap"])
    for s in biz:
        tag = "간판" if s["grade"] == "C" else s["license_type"]
        if s["start"]:
            events.append({"date": s["start"], "jibun": s["jibun"], "type": "business",
                           "event": "개업" if s["grade"] == "A" else "첫 간판 관찰",
                           "subject": s["name"], "detail": f"{tag} {s['floor']}".strip(),
                           "source": s["source"], "grade": s["grade"]})
        if s["end"] and s["end"][0].isdigit():
            events.append({"date": s["end"], "jibun": s["jibun"], "type": "business",
                           "event": "폐업" if s["grade"] == "A" else "마지막 간판 관찰",
                           "subject": s["name"], "detail": tag, "source": s["source"], "grade": s["grade"]})
    events.sort(key=lambda e: (e["jibun"], e["date"] if len(e["date"]) == 10 else obs_key(e["date"])))
    brows.sort(key=lambda b: (b["jibun"], b["end"] or "9999", b["start"]))
    write_csv(ROOT / "data/timeline_buildings.csv", brows)
    write_csv(ROOT / "data/timeline_businesses.csv", biz)
    write_csv(ROOT / "data/timeline_events.csv", events)

    from collections import Counter
    print("buildings", len(brows), Counter(b["status"] for b in brows))
    print("businesses", len(biz), Counter(s["grade"] for s in biz))
    fl = Counter(f.split(":")[0] for s in biz for f in s["flags"].split(";") if f)
    print("flags", fl)
    print("A spans with sign", sum(1 for s in biz if s["grade"] == "A" and s["sign_count"]))
    print("events", len(events))


if __name__ == "__main__":
    main()
