"""
Minimal HTTP service wrapping pymusiclooper.

POST /detect-loop
  Body: raw audio file bytes (any format ffmpeg can read)
  Content-Type: application/octet-stream (or audio/*)
  Returns 200 JSON:
    {
      "loop_start": <samples>,   # best candidate
      "loop_end":   <samples>,
      "candidates": [            # all top-N, best first
        {"loop_start": N, "loop_end": N, "score": 0.0–1.0},
        ...
      ]
    }
  Returns 404 JSON: { "error": "no loop detected" }
  Returns 500 JSON: { "error": "<message>" }

GET /health
  Returns 200 JSON: { "ok": true }
"""

import http.server
import json
import os
import re
import subprocess
import tempfile
import traceback


PORT = int(os.environ.get("PYMUSICLOOPER_PORT", "7070"))
TOP_N = int(os.environ.get("PYMUSICLOOPER_TOP_N", "5"))


def parse_candidates(stdout: str) -> list[dict]:
    """
    Parse --alt-export-top output.
    Each line: start_samples end_samples score1 score2 score3
    We use the last column (mse_score / composite) as the representative score.
    Lines that match the old LOOP_START/LOOP_END label format are also handled.
    """
    candidates = []

    # Try alt-export-top format first: lines of "int int float float float"
    for line in stdout.splitlines():
        line = line.strip()
        parts = line.split()
        if len(parts) >= 2:
            try:
                start = int(parts[0])
                end = int(parts[1])
                # Score: last numeric column if present, else 1.0
                score = float(parts[-1]) if len(parts) >= 3 else 1.0
                if end > start:
                    candidates.append({"loop_start": start, "loop_end": end, "score": round(score, 6)})
            except (ValueError, IndexError):
                continue

    if candidates:
        return candidates

    # Fallback: old LOOP_START / LOOP_END label format
    start_match = re.search(r"LOOP_START:\s*(\d+)", stdout, re.IGNORECASE)
    end_match   = re.search(r"LOOP_END:\s*(\d+)",   stdout, re.IGNORECASE)
    if start_match and end_match:
        s, e = int(start_match.group(1)), int(end_match.group(1))
        if e > s:
            return [{"loop_start": s, "loop_end": e, "score": 1.0}]

    return []


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
                    [
                        "pymusiclooper", "export-points",
                        "--path", audio_path,
                        "--alt-export-top", str(TOP_N),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=120,
                )

                print(f"[pymusiclooper] stdout: {result.stdout[:800]}", flush=True)
                if result.stderr:
                    print(f"[pymusiclooper] stderr: {result.stderr[:400]}", flush=True)

                candidates = parse_candidates(result.stdout)

                if not candidates:
                    self.send_json(404, {"error": "no loop detected"})
                    return

                best = candidates[0]
                self.send_json(200, {
                    "loop_start": best["loop_start"],
                    "loop_end":   best["loop_end"],
                    "candidates": candidates,
                })

        except subprocess.TimeoutExpired:
            self.send_json(500, {"error": "pymusiclooper timed out"})
        except Exception:
            self.send_json(500, {"error": traceback.format_exc()})


if __name__ == "__main__":
    server = http.server.HTTPServer(("0.0.0.0", PORT), Handler)
    print(f"[pymusiclooper] listening on port {PORT}", flush=True)
    server.serve_forever()
