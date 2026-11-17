"""로컬 서버: web/ 정적 파일 + POST /api/find (NDJSON 스트림). 실행: python3 server/app.py"""
import json, sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import agent, analysis

WEB = Path(__file__).resolve().parent.parent / "web"

_DB = None
def db():
    global _DB
    if _DB is None: _DB = agent.load_db()
    return _DB

FOCUS_WORDS = [("survival", ("버텼", "버티", "영업 기간", "영업기간", "얼마나 했", "오래", "생존", "폐업")),
               ("history", ("자리", "교체", "이력", "공실", "바뀌", "들어왔")),
               ("composition", ("업종", "구성", "비중", "종류", "많았", "줄었", "늘었"))]
def guess_focus(text):
    """LLM 없이 질문의 관점을 키워드로 짐작한다(에이전트가 해석하지 못할 때의 대체 경로)."""
    for f, ws in FOCUS_WORDS:
        if any(w in text for w in ws): return f
    return None

class H(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k): super().__init__(*a, directory=str(WEB), **k)
    def end_headers(self):                      # 개발 중 화면 파일이 브라우저에 캐시되어 옛 화면이 보이는 일을 막는다
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()
    def do_POST(self):
        if self.path not in ("/api/find", "/api/area"): self.send_error(404); return
        n = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(n) or b"{}")
        if self.path == "/api/area":
            rows, parcels = db()
            js = [j for j in (body.get("jibuns") or []) if isinstance(j, str) and j in parcels][:400]
            text = (body.get("text") or "").strip()[:500]
            out = json.dumps({"report": analysis.report(rows, parcels, js, guess_focus(text)), "text": text}, ensure_ascii=False).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(out))); self.end_headers(); self.wfile.write(out); return
        text = (body.get("text") or "").strip()[:500]
        state = body.get("state") if isinstance(body.get("state"), dict) else None
        self.send_response(200); self.send_header("Content-Type", "application/x-ndjson")
        self.send_header("Cache-Control", "no-store"); self.end_headers()
        def out(o): self.wfile.write((json.dumps(o, ensure_ascii=False) + "\n").encode()); self.wfile.flush()
        if not text: out({"step": "error", "msg": "단서를 입력해 주세요"}); return
        try:
            for ev in agent.run(text, state): out(ev)
        except Exception as e:                       # 키 값은 예외 메시지에 들어가지 않는다
            out({"step": "error", "msg": str(e)[:300]})

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    print(f"http://localhost:{port}"); ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
