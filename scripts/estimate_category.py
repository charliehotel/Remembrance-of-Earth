"""업소 시간표에 'AI 추정 업종' 컬럼(category_ai, category_ai_basis, category_ai_conf)을 채운다.

공식 업종(category·license_type)은 건드리지 않는다. 상호·간판 원문만 보고 업종이 분명하면 그대로 추정하고(basis=상호),
애매하면 웹 검색(Liner Search) 결과를 근거로 다시 판단한다(basis=웹검색 또는 상호+웹검색). 모르면 빈 값으로 둔다.
추정값은 공식 데이터가 아니므로 에이전트가 답변할 때 '추정'임을 밝혀야 한다.

대상: data/timeline_businesses.csv, data/timeline_businesses_r150.csv (두 파일에 열을 추가해 다시 쓴다. 여러 번 실행해도 같다)
캐시: data/category_ai_cache.json  (키: 상호|인허가유형|공식업종. 같은 키는 다시 부르지 않는다)
사용: .venv/bin/python -I scripts/estimate_category.py [--limit N] [--api] [--search] [--redo]
  --api   : 캐시에 없는 업소를 Liner Model API로 추정한다(외부 API 크레딧을 쓴다. 기본은 꺼짐)
  --search: 애매한 건을 Liner Search로 웹 검색해 보강한다(외부 API 크레딧을 쓴다. 기본은 꺼짐)
  --redo : 캐시를 무시하고 다시 추정
"""
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))
import liner, region  # noqa: E402

FILES = [ROOT / "data/timeline_businesses.csv", ROOT / "data/timeline_businesses_r150.csv"]
CACHE = ROOT / "data/category_ai_cache.json"
NEW_COLS = ["category_ai", "category_ai_basis", "category_ai_conf"]
SKIP_NAMES = {"", "상호", "상호판독보류"}
BATCH = 25

SCHEMA = {"type": "object", "additionalProperties": False, "required": ["items"], "properties": {"items": {
    "type": "array", "items": {"type": "object", "additionalProperties": False,
        "required": ["id", "category_ai", "conf", "need_search"],
        "properties": {"id": {"type": "string"}, "category_ai": {"type": "string"},
                       "conf": {"type": "string", "enum": ["높음", "보통", "낮음", "없음"]},
                       "need_search": {"type": "boolean"}}}}}}

SYS = ("너는 서울 서대문구 창천동·신촌 일대 가게의 업종을 상호로 추정하는 분류기다. 입력은 id | 상호 | 인허가 종류 | 공식 업태 | 층 | 간판 원문이다. "
       "각 가게의 업종을 사람이 가게를 부르는 짧은 일반명사 하나로 category_ai에 쓴다. 예: 치킨집, 편의점, 카페, 한식당, 중식당, 일식당, 양식당, 분식집, 고깃집, 족발·보쌈집, 피자집, "
       "햄버거집, 베이커리, 술집, 호프집, 노래방, 미용실, 네일샵, 약국, 병원, 학원, 부동산, 안경점, 옷가게, 화장품가게, 은행, 숙박업소, PC방, 세탁소, 서점, 문구점, 꽃집, 디저트카페, 아이스크림가게 등. "
       "목록에 없어도 되지만 '~집/~점/~실' 같은 평범한 이름을 쓴다. 인허가 종류나 공식 업태(예: 경양식, 일반음식점)를 그대로 옮기지 말고, 상호가 더 구체적으로 알려 주면 그것을 쓴다(네네치킨 → 치킨집). "
       "conf: 높음=상호만 봐도 업종이 분명함(GS25, 네네치킨, ○○약국), 보통=상호 느낌과 알려진 브랜드로 그럴듯함, 낮음=짐작에 가까움, 없음=상호에서 업종을 알 수 없음(category_ai는 빈 문자열). "
       "need_search: conf가 보통이하이고 웹 검색을 하면 확인될 가능성이 있으면 true. 지어내지 않는다. 모르면 conf=없음.")

SYS2 = ("너는 서울 서대문구 창천동·신촌 일대 가게의 업종을 정하는 분류기다. 가게마다 상호와 웹 검색 결과 요약이 주어진다. "
        "검색 결과가 이 가게(신촌·창천동 인근, 같은 상호)를 가리키는 경우에만 근거로 삼아 업종을 짧은 일반명사 하나(예: 치킨집, 카페, 술집)로 category_ai에 쓴다. "
        "검색 결과가 다른 지역의 같은 이름이거나 업종을 알 수 없으면 앞서 추정한 값(prev)을 conf 그대로 두거나 낮추고, 정말 모르면 빈 문자열과 conf=없음으로 쓴다. "
        "conf: 높음=검색 결과가 직접 업종을 말함, 보통=정황상 그럴듯함, 낮음=짐작, 없음=모름. used_web은 검색 결과를 근거로 썼으면 true.")

SCHEMA2 = {"type": "object", "additionalProperties": False, "required": ["items"], "properties": {"items": {
    "type": "array", "items": {"type": "object", "additionalProperties": False,
        "required": ["id", "category_ai", "conf", "used_web"],
        "properties": {"id": {"type": "string"}, "category_ai": {"type": "string"},
                       "conf": {"type": "string", "enum": ["높음", "보통", "낮음", "없음"]},
                       "used_web": {"type": "boolean"}}}}}}


def key(r):
    return f"{r['name']}|{r['license_type']}|{r['category']}"


def read(path):
    return list(csv.DictReader(path.open(encoding="utf-8-sig")))


def line(i, r):
    return f"{i} | {r['name']} | {r['license_type'] or '-'} | {r['category'] or '-'} | {r['floor'] or '-'} | {(r['observed_as'] or '-')[:80]}"


def first_pass(items, cache):
    for s in range(0, len(items), BATCH):
        chunk = items[s:s + BATCH]
        user = "\n".join(line(str(i), r) for i, r in enumerate(chunk))
        res, _, cost = liner.chat_json(SYS, user, SCHEMA, "estimate", 3000)
        got = {x["id"]: x for x in res["items"]}
        for i, r in enumerate(chunk):
            x = got.get(str(i))
            if not x:
                continue
            conf = x["conf"]
            cat = x["category_ai"].strip() if conf != "없음" else ""
            cache[key(r)] = {"category_ai": cat, "conf": conf if cat else "없음", "basis": "상호" if cat else "",
                             "need_search": bool(x["need_search"]) and conf != "높음"}
        print(f"  1차 {min(s + BATCH, len(items))}/{len(items)} (${cost:.4f})", flush=True)
        save(cache)


def search_pass(items, cache):
    for s in range(0, len(items), 10):
        chunk = items[s:s + 10]
        lines = []
        for i, r in enumerate(chunk):
            try:
                hits = liner.search(f"{r['name']} {region.R['district']} {region.DONG}", 5)
            except Exception as e:  # noqa: BLE001
                print("  search fail", r["name"], type(e).__name__)
                hits = []
            snip = " / ".join(f"{h['title'][:50]}: {h['desc'][:100]}" for h in hits) or "(검색 결과 없음)"
            prev = cache[key(r)]
            lines.append(f"{i} | 상호:{r['name']} | prev:{prev['category_ai'] or '-'}({prev['conf']}) | 검색: {snip}")
        res, _, cost = liner.chat_json(SYS2, "\n".join(lines), SCHEMA2, "estimate_web", 3000)
        got = {x["id"]: x for x in res["items"]}
        for i, r in enumerate(chunk):
            c = cache[key(r)]
            c["need_search"] = False
            c["searched"] = True
            x = got.get(str(i))
            if not x:
                continue
            cat = x["category_ai"].strip() if x["conf"] != "없음" else ""
            if x["used_web"] and cat:
                c.update(category_ai=cat, conf=x["conf"], basis="상호+웹검색" if c["basis"] else "웹검색")
            elif cat and not c["category_ai"]:
                c.update(category_ai=cat, conf=x["conf"], basis="상호")
        print(f"  웹 {min(s + 10, len(items))}/{len(items)} (${cost:.4f})", flush=True)
        save(cache)


def save(cache):
    CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=0), encoding="utf-8")


def main():
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    cache = {} if "--redo" in sys.argv else (json.loads(CACHE.read_text()) if CACHE.exists() else {})
    tables = {p: read(p) for p in FILES if p.exists()}
    uniq = {}
    for rows in tables.values():
        for r in rows:
            if r["name"] not in SKIP_NAMES:
                uniq.setdefault(key(r), r)
    todo = [r for k, r in uniq.items() if k not in cache]
    if limit:
        todo = todo[:limit]
    print(f"고유 업소 {len(uniq)}건, 새로 추정 {len(todo)}건")
    if todo and "--api" in sys.argv:
        first_pass(todo, cache)                      # 외부 API(Liner) 크레딧을 쓴다. 기본은 꺼짐
    elif todo:
        print("캐시에 없는 업소가 있다. Claude Code 세션에서 캐시를 채우거나 --api 로 Liner 를 쓴다.")
    if "--search" in sys.argv:
        need = [r for k, r in uniq.items() if k in cache and cache[k].get("need_search")]
        print(f"웹 검색 대상 {len(need)}건")
        search_pass(need, cache)
    for path, rows in tables.items():
        for r in rows:
            c = cache.get(key(r)) if r["name"] not in SKIP_NAMES else None
            r["category_ai"] = c["category_ai"] if c else ""
            r["category_ai_basis"] = c["basis"] if c and c["category_ai"] else ""
            r["category_ai_conf"] = c["conf"] if c and c["category_ai"] else ""
        fields = [f for f in rows[0] if f not in NEW_COLS] + NEW_COLS
        with path.open("w", encoding="utf-8-sig", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)
        filled = sum(bool(r["category_ai"]) for r in rows)
        print(f"{path.name}: {filled}/{len(rows)} 행에 추정 업종")


if __name__ == "__main__":
    main()
