"""로컬 서버: web/ 정적 파일 + POST /api/find (NDJSON 스트림). 실행: python3 server/app.py"""
import json, sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import agent

WEB = Path(__file__).resolve().parent.parent / "web"

class H(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k): super().__init__(*a, directory=str(WEB), **k)
    def end_headers(self):                      # 개발 중 화면 파일이 브라우저에 캐시되어 옛 화면이 보이는 일을 막는다
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()
    def do_POST(self):
        if self.path != "/api/find": self.send_error(404); return
        n = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(n) or b"{}")
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
