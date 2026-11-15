"""150m 확장 필지(in_core=False)의 건물 시간표를 만든다. build_timeline.buildings() 로직을 그대로 쓰되
HUB 원본만 *_r150.json 으로 바꿔 읽고, 기존 data/timeline_*.csv 는 건드리지 않는다.

출력: data/timeline_buildings_r150.csv, data/timeline_events_r150.csv(건물 이벤트만)
  + 필지별 점검 열 end_note: 말소·철거 날짜가 없으면 '날짜 미상', 현존 건물보다 말소가 늦으면 '겹침' 등.

사용: .venv/bin/python -I scripts/build_timeline_r150.py
"""
import csv
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import build_timeline as bt  # noqa: E402

_orig_load = bt.load
bt.load = lambda name: _orig_load(f"{name}_r150")


def main():
    brows, events = bt.buildings()
    by = defaultdict(list)
    for r in brows:
        by[r["jibun"]].append(r)
    for jibun, rs in by.items():
        live = [r for r in rs if r["status"] == "현존"]
        for r in rs:
            note = ""
            if r["status"] != "현존":
                if not r["end"]:
                    note = "말소·철거 날짜 미상"
                elif live and any(l["start"] and r["end"] > l["start"] and r["start"] and r["start"] < l["start"] for l in live):
                    note = ""  # 정상: 옛 건물 말소 후 신축
                elif live and any(l["start"] and l["start"] < r["end"] for l in live):
                    note = "현존 건물이 더 먼저 승인됨(말소는 별동·일부일 수 있음)"
            r["end_note"] = note
    brows.sort(key=lambda r: (r["jibun"], r["start"] or "0"))
    for name, rows in (("timeline_buildings_r150.csv", brows),
                       ("timeline_events_r150.csv", sorted(events, key=lambda e: (e["date"], e["jibun"])))):
        with (ROOT / "data" / name).open("w", encoding="utf-8-sig", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
    undated = [r for r in brows if r["status"] != "현존" and not r["end"]]
    print(f"건물행={len(brows)} (현존 {sum(r['status']=='현존' for r in brows)}), 이벤트={len(events)}, "
          f"말소·철거 날짜 없음={len(undated)}")


if __name__ == "__main__":
    main()
