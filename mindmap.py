"""
mindmap_server.py — Serves the News Mindmap UI.

Run:  py mindmap_server.py
Opens: http://localhost:8765

Endpoints:
  GET  /           -> mindmap.html
  GET  /api/news   -> current news_results_end.json
  POST /api/refresh -> run aggregator.py + agents.py, stream SSE output
"""

import json
import subprocess
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

PORT = 8765
BASE_DIR = Path(__file__).parent


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ('/', '/mindmap.html'):
            self._serve_file(BASE_DIR / 'mindmap.html', 'text/html; charset=utf-8')
        elif self.path == '/api/news':
            path = BASE_DIR / 'news_results_end.json'
            data = path.read_text(encoding='utf-8') if path.exists() else '[]'
            self._send_json(data)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == '/api/refresh':
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.send_header('Cache-Control', 'no-cache')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self._run_pipeline()
        else:
            self.send_response(404)
            self.end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.end_headers()

    def _serve_file(self, path: Path, content_type: str):
        if not path.exists():
            self.send_response(404)
            self.end_headers()
            return
        data = path.read_bytes()
        self.send_response(200)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_json(self, data: str):
        enc = data.encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(enc)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(enc)

    def _sse(self, msg: str):
        try:
            line = f'data: {json.dumps(msg)}\n\n'.encode('utf-8')
            self.wfile.write(line)
            self.wfile.flush()
        except Exception:
            pass

    def _run_pipeline(self):
        for script in ['aggregator.py', 'agents.py']:
            self._sse(f'=== Running {script} ===')
            try:
                proc = subprocess.Popen(
                    [sys.executable, str(BASE_DIR / script)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding='utf-8',
                    errors='replace',
                    cwd=str(BASE_DIR),
                )
                for line in proc.stdout:
                    self._sse(line.rstrip())
                proc.wait()
                if proc.returncode != 0:
                    self._sse(f'ERROR: {script} exited with code {proc.returncode}')
                    break
            except Exception as e:
                self._sse(f'ERROR launching {script}: {e}')
                break
        self._sse('DONE')

    def log_message(self, *args):
        pass  # suppress per-request logs


def _open_browser():
    import time
    time.sleep(0.6)
    webbrowser.open(f'http://localhost:{PORT}')


if __name__ == '__main__':
    print(f'[mindmap] Serving at http://localhost:{PORT}')
    print(f'[mindmap] Press Ctrl+C to stop')
    threading.Thread(target=_open_browser, daemon=True).start()
    server = HTTPServer(('localhost', PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\n[mindmap] Stopped.')
