"""간판만 확인된 상호(timeline_businesses.csv 의 grade C)를 카카오 다음 검색(블로그·카페·웹)으로 찾아
언급 날짜를 data/review_web_mentions.csv 로 낸다. 등급 D(웹 언급) 후보이며 자동 반영하지 않는다.

주의
- 글의 작성일은 영업 시기가 아니라 글을 쓴 날이다. '그 무렵 존재했다'는 약한 존재 증거일 뿐이다.
- 상호가 제목·본문에 그대로 들어간 결과만 남기고, 같은 이름의 다른 가게일 수 있어 지역 단어(신촌·창천·연세로)가
  함께 나온 것만 `local=1` 로 표시한다.
- 키는 .env 의 KAKAO_REST_API_KEY. 값은 출력하지 않는다.
- 결과는 data/raw/kakao/ 에 원본을 캐시한다(재실행 시 다시 부르지 않는다).
사용: .venv/bin/python -I scripts/web_mentions.py [--limit N]
"""
import csv
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts")); sys.path.insert(0, str(ROOT / "server"))
import region  # noqa: E402
from crosscheck import norm  # noqa: E402

CACHE = ROOT / "data/raw/kakao"
ENDPOINT = "https://dapi.kakao.com/v2/search/{}"
KINDS = ("blog", "cafe", "web")
LOCAL = re.compile("|".join(region.R["name_strip"][:1] + [region.DONG[:-1], region.R["core_name"][:3]]))
TAG = re.compile(r"<[^>]+>")


def key():
    for line in (ROOT / ".env").read_text().splitlines():
        if line.startswith("KAKAO_REST_API_KEY="):
            return line.split("=", 1)[1].strip()
    sys.exit("KAKAO_REST_API_KEY 없음")


def query_text(row):
    """정규화된 key(공백 없음) 대신 간판 원문에서 같은 이름의 띄어쓰기 표기를 찾는다."""
    for raw in row["observed_as"].split(" | "):
        s = re.sub(r"\([^)]*\)", " ", raw)
        for part in re.split(r"[·/,]", s):
            if norm(part) == row["name"] or row["name"] in norm(part):
                return part.strip() or row["name"]
    return row["name"]


def fetch(kind, q, k):
    f = CACHE / f"{kind}_{norm(q)}.json"
    if f.exists():
        return json.loads(f.read_text())
    url = ENDPOINT.format(kind) + "?" + urllib.parse.urlencode({"query": q, "size": 30})
    req = urllib.request.Request(url, headers={"Authorization": f"KakaoAK {k}"})
    try:
        data = json.load(urllib.request.urlopen(req, timeout=20))
    except Exception as e:  # noqa: BLE001
        print("  fail", kind, q, type(e).__name__)
        return None
    CACHE.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(data, ensure_ascii=False))
    time.sleep(0.2)
    return data


def main():
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    k = key()
    rows = [r for r in csv.DictReader(open(ROOT / "data/timeline_businesses.csv", encoding="utf-8-sig"))
            if r["grade"] == "C" and len(r["name"]) >= 3]
    if limit:
        rows = rows[:limit]
    out = []
    for r in rows:
        q = query_text(r)
        qn = norm(q)
        hits = []
        for kind in KINDS:
            data = fetch(kind, f"신촌 {q}", k)
            for d in (data or {}).get("documents", []):
                title = TAG.sub("", d.get("title", ""))
                body = TAG.sub("", d.get("contents", ""))
                if qn not in norm(title + body):
                    continue
                date = (d.get("datetime") or d.get("date") or "")[:10]
                hits.append({"jibun": r["jibun"], "name": r["name"], "query": q,
                             "sign_first": r["sign_first"], "sign_last": r["sign_last"],
                             "kind": kind, "post_date": date, "title": title[:80],
                             "local": int(bool(LOCAL.search(title + body))), "url": d.get("url", ""),
                             "decision": ""})
        out += hits
        dates = sorted(h["post_date"] for h in hits if h["local"] and h["post_date"])
        print(f"{r['jibun']:6} {q[:20]:20} hits {len(hits):3} local {len(dates):3}",
              f"{dates[0]}~{dates[-1]}" if dates else "")
    if out:
        out.sort(key=lambda h: (h["jibun"], h["name"], h["post_date"]))
        with open(ROOT / "data/review_web_mentions.csv", "w", encoding="utf-8-sig", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(out[0]))
            w.writeheader()
            w.writerows(out)
    print("names", len(rows), "mentions", len(out))


if __name__ == "__main__":
    main()
