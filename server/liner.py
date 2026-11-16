"""Liner API 클라이언트 (표준 라이브러리만 사용).
키는 환경 변수 LINER_API_KEY 또는 프로젝트 .env 에서 읽는다. 값은 출력하지 않는다."""
import json, os, time, urllib.request, urllib.error
from pathlib import Path

BASE = "https://platform.liner.com/api/v1"
MODEL = os.environ.get("LINER_MODEL", "anthropic/claude-haiku-5.5")   # 게이트웨이로 haiku 지정
FALLBACK_MODEL = "liner-claude-router"                                   # 지정 모델이 거부되면 라우터(비용 우선)

def _key():
    k = os.environ.get("LINER_API_KEY")
    if k: return k
    env = Path(__file__).resolve().parent.parent / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith("LINER_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"\'')
    raise RuntimeError("LINER_API_KEY 없음: .env 에 LINER_API_KEY=... 를 넣어 주세요")

def _post(path, body, timeout=60, retries=2):
    data = json.dumps(body).encode()
    last = None
    for i in range(retries + 1):
        req = urllib.request.Request(BASE + path, data=data, method="POST",
            headers={"x-api-key": _key(), "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            msg = e.read().decode("utf-8", "ignore")[:300]
            last = RuntimeError(f"Liner {path} HTTP {e.code}: {msg}")
            if e.code in (429, 502, 503, 504, 524) and i < retries:
                time.sleep(2 * (i + 1)); continue
            raise last
        except (urllib.error.URLError, TimeoutError) as e:
            last = RuntimeError(f"Liner {path} 연결 실패: {e}")
            if i < retries: time.sleep(2); continue
            raise last
    raise last

def search(query, max_results=5, lang="ko"):
    """Liner Search API (웹). 호출당 약 $0.001."""
    r = _post("/tools/search/web", {"query": query, "lang": lang, "max_results": max_results,
                                    "include_knowledge": False})
    return [{"title": x.get("title", ""), "url": x.get("url", ""), "desc": x.get("description", ""),
             "date": x.get("date", ""), "hostname": x.get("hostname", "")} for x in r.get("results", [])]

def chat_json(system, user, schema, name="result", max_tokens=1500):
    """Liner Model API. JSON 스키마 출력. 반환: (파싱된 dict, 사용 모델, 비용).
    응답이 잘리거나 JSON이 깨지면 토큰 한도를 늘려 한 번 더 시도한다."""
    model, cost_total, last = MODEL, 0.0, None
    for attempt in range(2):
        body = {"model": model, "max_completion_tokens": int(max_tokens * (1 + attempt)), "reasoning_effort": "low",
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                "response_format": {"type": "json_schema",
                                    "json_schema": {"name": name, "schema": schema, "strict": True}}}
        if model == FALLBACK_MODEL: body["routing_strategy"] = "cost"
        try:
            r = _post("/chat/completions", body)
        except RuntimeError as e:
            if model != FALLBACK_MODEL and ("HTTP 400" in str(e) or "HTTP 404" in str(e)):
                model = FALLBACK_MODEL; body["model"] = model; body["routing_strategy"] = "cost"
                r = _post("/chat/completions", body)
            else:
                raise
        cost_total += (r.get("usage") or {}).get("cost") or 0
        ch = r["choices"][0]
        try:
            return json.loads(ch["message"]["content"]), r.get("model", model), cost_total
        except (json.JSONDecodeError, TypeError) as e:
            last = RuntimeError(f"모델 응답을 해석하지 못했습니다(finish_reason={ch.get('finish_reason')}): {e}")
    raise last
