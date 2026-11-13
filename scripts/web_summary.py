"""review_web_mentions.csv 를 상호별로 요약해 data/web_mentions_summary.csv 를 낸다.

걸러내는 것
- 날짜 없는 글(1970-01-01)과 2000년 이전 날짜
- 지역 단어(신촌·창천·연세로)가 없는 글 (local=0)
- 같은 url 중복
- GENERIC: 일반명사·체인·흔한 이름이라 다른 가게 글이 섞이는 상호. 요약하지 않고 `generic=1` 로만 남긴다.
요약 값
- web_first / web_last: 남은 글의 최초·최신 작성일 (영업 시기가 아니라 글 작성일)
- web_n: 남은 글 수, web_title_n: 그중 제목에 상호가 있는 글 수(신뢰도 높음)
- web_state: strong(제목 언급 ≥3) / weak(그 외 언급 있음) / none / generic
- overlap: 간판 관찰 구간(sign_first~sign_last)과 같은 시기 글이 있는지(±1년 포함)
사용: .venv/bin/python -I scripts/web_summary.py
"""
import csv
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from crosscheck import norm  # noqa: E402

GENERIC = {norm(x) for x in [
    "부대찌개", "아구찜", "해물찜", "PASTA", "JOY", "GS25", "굽네치킨", "사주카페", "술 카페", "함흥냉면",
    "오뎅 BAR", "TRB", "베네핏 필라테스", "solv 필라테스&바레", "카페다이렉트", "신촌 서서갈비",
    "돈까스 참 잘하는 집", "상호 판독 보류", "외벽 붉은 글씨", "매장 리모델링 중", "만화 cafe",
    "Cafe & Hookah Lounge", "Leann", "Le Ann Flowers", "Le Ann Flower 현수막", "만화공화국", "만화나라",
]}


def year(s):
    return int(s[:4])


def obs_year(s):
    return int(s[:4]) if s else None


def main():
    ment = list(csv.DictReader(open(ROOT / "data/review_web_mentions.csv", encoding="utf-8-sig")))
    by = defaultdict(list)
    for m in ment:
        by[(m["jibun"], m["name"])].append(m)
    biz = [b for b in csv.DictReader(open(ROOT / "data/timeline_businesses.csv", encoding="utf-8-sig")) if b["grade"] == "C"]
    out = []
    for b in biz:
        key = (b["jibun"], b["name"])
        rows = by.get(key, [])
        qn = norm(rows[0]["query"]) if rows else b["name"]
        seen, keep = set(), []
        for m in rows:
            if m["local"] != "1" or not m["post_date"] or year(m["post_date"]) < 2000 or m["url"] in seen:
                continue
            seen.add(m["url"])
            keep.append(m)
        dates = sorted(m["post_date"] for m in keep)
        title_n = sum(1 for m in keep if qn in norm(m["title"]))
        generic = b["name"] in GENERIC or norm(rows[0]["query"] if rows else "") in GENERIC
        if generic:
            state = "generic"
        elif not keep:
            state = "none"
        else:
            state = "strong" if title_n >= 3 else "weak"
        ov = ""
        if state in ("strong", "weak") and b["sign_first"]:
            lo, hi = obs_year(b["sign_first"]) - 1, obs_year(b["sign_last"]) + 1
            ov = int(any(lo <= year(d) <= hi for d in dates))
        out.append({"jibun": b["jibun"], "name": b["name"], "sign_first": b["sign_first"], "sign_last": b["sign_last"],
                    "web_state": state,
                    "web_first": dates[0] if state in ("strong", "weak") else "",
                    "web_last": dates[-1] if state in ("strong", "weak") else "",
                    "web_n": len(keep) if state in ("strong", "weak") else "",
                    "web_title_n": title_n if state in ("strong", "weak") else "",
                    "overlap": ov})
    with open(ROOT / "data/web_mentions_summary.csv", "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)
    from collections import Counter
    print(Counter(o["web_state"] for o in out))
    for o in out:
        if o["web_state"] in ("strong", "weak"):
            print(f"{o['jibun']:6} {o['name'][:16]:16} {o['web_state']:6} 간판 {o['sign_first']}~{o['sign_last']}"
                  f" 글 {o['web_first']}~{o['web_last']} n={o['web_n']} title={o['web_title_n']} overlap={o['overlap']}")


if __name__ == "__main__":
    main()
