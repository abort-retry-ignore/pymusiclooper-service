"""
Minimal HTTP service wrapping pymusiclooper.

POST /detect-loop
  Body: raw audio file bytes (any format ffmpeg can read)
  Content-Type: application/octet-stream (or audio/*)
  Returns 200 JSON: { "loop_start": <samples>, "loop_end": <samples> }
           404 JSON: { "error": "no loop detected" }
           500 JSON: { "error": "<message>" }

GET /health
  Returns 200 JSON: { "ok": true }
"""

import http.server
import json
import os
import subprocess
import tempfile
import traceback


PORT = int(os.environ.get("PYMUSICLOOPER_PORT", "7070"))


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):  # noqa: A002
        print(f"[pymusiclooper] {self.address_string()} - {format % args}", flush=True)

    def send_json(self, code: int, body: dict):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/health":
            self.send_json(200, {"ok": True})
        else:
            self.send_json(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/detect-loop":
            self.send_json(404, {"error": "not found"})
            return

        length = int(self.headers.get("Content-Length", 0))
        if length <= 0:
            self.send_json(400, {"error": "empty body"})
            return

        audio_bytes = self.rfile.read(length)

        try:
            with tempfile.TemporaryDirectory() as tmp:
                audio_path = os.path.join(tmp, "audio.mp3")
                with open(audio_path, "wb") as f:
                    f.write(audio_bytes)

                result = subprocess.run(
                    ["pymusiclooper", "export-points", "--path", audio_path],
                    capture_output=True,
                    text=True,
                    timeout=120,
                )

                output = result.stdout + result.stderr
                print(f"[pymusiclooper] stdout: {result.stdout[:500]}", flush=True)
                if result.stderr:
                    print(f"[pymusiclooper] stderr: {result.stderr[:500]}", flush=True)

                import re
                start_match = re.search(r"LOOP_START:\s*(\d+)", output, re.IGNORECASE)
                end_match = re.search(r"LOOP_END:\s*(\d+)", output, re.IGNORECASE)

                if not start_match or not end_match:
                    self.send_json(404, {"error": "no loop detected"})
                    return

                loop_start = int(start_match.group(1))
                loop_end = int(end_match.group(1))

                if loop_end <= loop_start:
                    self.send_json(404, {"error": "invalid loop points"})
                    return

                self.send_json(200, {"loop_start": loop_start, "loop_end": loop_end})

        except subprocess.TimeoutExpired:
            self.send_json(500, {"error": "pymusiclooper timed out"})
        except Exception:
            self.send_json(500, {"error": traceback.format_exc()})


if __name__ == "__main__":
    server = http.server.HTTPServer(("0.0.0.0", PORT), Handler)
    print(f"[pymusiclooper] listening on port {PORT}", flush=True)
    server.serve_forever()
