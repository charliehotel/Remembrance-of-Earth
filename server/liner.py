"""Liner API 클라이언트 (표준 라이브러리만 사용).
키는 환경 변수 LINER_API_KEY 또는 프로젝트 .env 에서 읽는다. 값은 출력하지 않는다."""
import json, os, time, urllib.request, urllib.error
from pathlib import Path

BASE = "https://platform.liner.com/api/v1"
MODEL = os.environ.get("LINER_MODEL", "anthropic/claude-haiku-5.5")   # 게이트웨이로 haiku 지정
FALLBACK_MODEL = "liner-claude-router"                                   # 지정 모델이 거부되면 라우터(비용 우선)

def _envval(name):
    """환경 변수 → 프로젝트 .env 순으로 값을 읽는다(값은 출력하지 않는다)."""
    v = os.environ.get(name)
    if v: return v
    env = Path(__file__).resolve().parent.parent / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith(name + "="):
                return line.split("=", 1)[1].strip().strip('"\'')
    return None

def provider():
    """모델 호출 공급자. 기본은 liner. 개발·테스트 중에는 .env 에 LLM_PROVIDER=cliproxyapi."""
    return (_envval("LLM_PROVIDER") or "liner").strip().lower()

def _keys():
    """사용할 키 목록(기본 → fallback). 환경 변수가 .env 보다 우선한다."""
    vals = {"LINER_API_KEY": os.environ.get("LINER_API_KEY"),
            "LINER_API_KEY_fallback": os.environ.get("LINER_API_KEY_fallback")}
    env = Path(__file__).resolve().parent.parent / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            for name in vals:
                if not vals[name] and line.startswith(name + "="):
                    vals[name] = line.split("=", 1)[1].strip().strip('"\'')
    keys = [v for v in vals.values() if v]
    if not keys:
        raise RuntimeError("LINER_API_KEY 없음: .env 에 LINER_API_KEY=... 를 넣어 주세요")
    return list(dict.fromkeys(keys))

_active = 0   # 현재 쓰는 키 번호. 기본 키가 인증·잔액 오류를 내면 fallback으로 넘어가 이후에도 유지한다.
AUTH_FAIL = (401, 402, 403)

def _post(path, body, timeout=60, retries=2):
    global _active
    data = json.dumps(body).encode()
    last = None
    i = 0
    while i <= retries:
        keys = _keys()
        req = urllib.request.Request(BASE + path, data=data, method="POST",
            headers={"x-api-key": keys[min(_active, len(keys) - 1)], "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            msg = e.read().decode("utf-8", "ignore")[:300]
            last = RuntimeError(f"Liner {path} HTTP {e.code}: {msg}")
            if e.code in AUTH_FAIL and _active < len(keys) - 1:
                _active += 1; continue          # 다음 키로 즉시 재시도(재시도 횟수는 쓰지 않음)
            if e.code in (429, 502, 503, 504, 524) and i < retries:
                time.sleep(2 * (i + 1)); i += 1; continue
            raise last
        except (urllib.error.URLError, TimeoutError) as e:
            last = RuntimeError(f"Liner {path} 연결 실패: {e}")
            if i < retries: time.sleep(2); i += 1; continue
            raise last
    raise last

def search(query, max_results=5, lang="ko"):
    """Liner Search API (웹). 호출당 약 $0.001. LLM_PROVIDER=cliproxyapi 이면 프록시의 구글 검색으로 대신한다."""
    if provider() == "cliproxyapi":
        return _search_proxy(query, max_results)
    r = _post("/tools/search/web", {"query": query, "lang": lang, "max_results": max_results,
                                    "include_knowledge": False})
    return [{"title": x.get("title", ""), "url": x.get("url", ""), "desc": x.get("description", ""),
             "date": x.get("date", ""), "hostname": x.get("hostname", "")} for x in r.get("results", [])]

def chat_json(system, user, schema, name="result", max_tokens=1500):
    """Liner Model API. JSON 스키마 출력. 반환: (파싱된 dict, 사용 모델, 비용).
    응답이 잘리거나 JSON이 깨지면 토큰 한도를 늘려 한 번 더 시도한다."""
    if provider() == "cliproxyapi":
        return _chat_json_proxy(system, user, schema, name, max_tokens)
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


# ---------- 개발·테스트용: CLIProxyAPI(OpenAI 호환) ----------
def _proxy_post(body, timeout=120, retries=2):
    base = (_envval("CLIProxyAPI_LLM_BASE_URL") or "").rstrip("/")
    key = _envval("CLIProxyAPI_LLM_API_KEY")
    if not base or not key:
        raise RuntimeError(".env 에 CLIProxyAPI_LLM_BASE_URL / CLIProxyAPI_LLM_API_KEY 가 필요합니다")
    data, last = json.dumps(body).encode(), None
    for i in range(retries + 1):
        req = urllib.request.Request(base + "/chat/completions", data=data, method="POST",
            headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            msg = e.read().decode("utf-8", "ignore")[:300]
            last = RuntimeError(f"프록시 HTTP {e.code}: {msg}")
            if e.code in (429, 502, 503, 504, 524) and i < retries:
                time.sleep(2 * (i + 1)); continue
            raise last
        except (urllib.error.URLError, TimeoutError) as e:
            last = RuntimeError(f"프록시 연결 실패: {e}")
            if i < retries: time.sleep(2); continue
            raise last
    raise last

def _parse_json_text(text):
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.strip("`").removeprefix("json").strip()
    a, b = t.find("{"), t.rfind("}")
    return json.loads(t[a:b + 1] if a >= 0 and b > a else t)

def _chat_json_proxy(system, user, schema, name, max_tokens):
    """구조화 출력(json_schema)을 먼저 시도하고, 프록시가 거부(400)하면 스키마를 프롬프트에 넣는 방식으로 바꾼다."""
    model = _envval("CLIProxyAPI_LLM_MODEL")
    if not model: raise RuntimeError(".env 에 CLIProxyAPI_LLM_MODEL 이 필요합니다")
    use_schema, last = True, None
    for attempt in range(2):
        sysmsg = system if use_schema else system + "\n\n반드시 아래 JSON 스키마를 따르는 JSON 객체 하나만 출력하세요(설명·코드블록 금지):\n" + json.dumps(schema, ensure_ascii=False)
        body = {"model": model, "max_tokens": int(max_tokens * 2 * (1 + attempt)),
                "messages": [{"role": "system", "content": sysmsg}, {"role": "user", "content": user}]}
        if use_schema:
            body["response_format"] = {"type": "json_schema", "json_schema": {"name": name, "schema": schema, "strict": True}}
        try:
            r = _proxy_post(body)
        except RuntimeError as e:
            if use_schema and "HTTP 400" in str(e):
                use_schema = False; continue
            raise
        ch = r["choices"][0]
        try:
            return _parse_json_text(ch["message"]["content"]), r.get("model", model), 0.0
        except (json.JSONDecodeError, TypeError, ValueError) as e:
            last = RuntimeError(f"모델 응답을 해석하지 못했습니다(finish_reason={ch.get('finish_reason')}): {e}")
    raise last


def _resolve_redirect(uri, timeout=15):
    """구글 grounding 중계 주소를 따라가 원문 주소를 얻는다. 실패하면 받은 주소를 그대로 쓴다."""
    try:
        req = urllib.request.Request(uri, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.geturl()
    except Exception:
        return uri

def _search_proxy(query, max_results=5):
    """개발·테스트용 웹 검색: 프록시의 Gemini 원본 API(generateContent)에 googleSearch 도구를 켜서
    grounding 출처를 Liner Search 와 같은 모양(title/url/desc/date/hostname)으로 돌려준다.
    desc 는 모델 답변 중 그 출처가 뒷받침하는 구절이다."""
    base = (_envval("CLIProxyAPI_LLM_BASE_URL") or "").rstrip("/")
    key, model = _envval("CLIProxyAPI_LLM_API_KEY"), _envval("CLIProxyAPI_LLM_MODEL")
    if not (base and key and model):
        raise RuntimeError(".env 에 CLIProxyAPI_LLM_BASE_URL / API_KEY / MODEL 이 필요합니다")
    root = base[:-3] if base.endswith("/v1") else base
    body = {"contents": [{"role": "user", "parts": [{"text": f"웹을 검색해서 다음 내용을 찾아 출처와 함께 정리해줘: {query}"}]}],
            "tools": [{"googleSearch": {}}]}
    data, d, last = json.dumps(body).encode(), None, None
    for i in range(3):
        req = urllib.request.Request(f"{root}/v1beta/models/{model}:generateContent", data=data, method="POST",
            headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                d = json.loads(r.read()); break
        except urllib.error.HTTPError as e:
            last = RuntimeError(f"프록시 검색 HTTP {e.code}: {e.read().decode('utf-8', 'ignore')[:200]}")
            if e.code in (429, 502, 503, 504, 524) and i < 2: time.sleep(2 * (i + 1)); continue
            raise last
        except (urllib.error.URLError, TimeoutError) as e:
            last = RuntimeError(f"프록시 검색 연결 실패: {e}")
            if i < 2: time.sleep(2); continue
            raise last
    cands = (d or {}).get("candidates") or []
    g = (cands[0].get("groundingMetadata") or {}) if cands else {}
    chunks = g.get("groundingChunks") or []
    parts = {}
    for sup in g.get("groundingSupports") or []:
        for idx in sup.get("groundingChunkIndices") or []:
            parts.setdefault(idx, []).append((sup.get("segment") or {}).get("text", "").strip())
    out, seen = [], set()
    for i, ch in enumerate(chunks):
        w = ch.get("web") or {}
        if not w.get("uri"): continue
        url = _resolve_redirect(w["uri"])
        if url in seen: continue
        seen.add(url)
        host = w.get("title", "")
        out.append({"title": host, "url": url, "desc": " ".join(x for x in parts.get(i, []) if x).replace("**", "")[:400],
                    "date": "", "hostname": host})
        if len(out) >= max_results: break
    return out
