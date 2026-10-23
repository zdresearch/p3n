"""The AI detection oracle the skills call: today tropa-mini (tropa.py next to this file). The skills call this name, so
the oracle can change without editing them.

  python3 oracle.py FILE                 the classifier block of ai-detection's judge input
  python3 oracle.py FILE FILE...         one line per file: ai score, top label, "(passes)" unless the top label is ai
  python3 oracle.py FILE... --json       everything
  python3 oracle.py --keep-alive         load the model once in the background; later calls use it (no load each time)
  python3 oracle.py --stop               stop the background oracle

Each call loads the model (about 5 s on CPU), scores, and exits; files given together share one load. With
--keep-alive, calls (in parallel too) go to the one loaded model, scored one at a time, so memory stays at one model
(~2.2 GB). It listens on 127.0.0.1 only, with a secret in ~/.cache/p3n/oracle.json (readable by the user alone), and
exits on --stop or after 10 minutes without work (P3N_ORACLE_IDLE, in seconds), so a forgotten one
unloads itself.
"""
from __future__ import annotations

import json
import os
import secrets
import subprocess
import sys
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tropa  # noqa: E402

STATE = Path.home() / '.cache' / 'p3n' / 'oracle.json'
IDLE_SECONDS = int(os.environ.get('P3N_ORACLE_IDLE', 600))  # unloads itself after 10 minutes without work
START_SECONDS = 600  # the first start downloads ~1.7 GB


def _state() -> dict | None:
    try:
        return json.loads(STATE.read_text())
    except (OSError, ValueError):
        return None


def _ask(st: dict, path: str, body: dict, timeout: float) -> dict:
    req = urllib.request.Request(f"http://127.0.0.1:{st['port']}{path}", json.dumps(body).encode(),
                                 {'Content-Type': 'application/json', 'X-Oracle-Secret': st['secret']})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def _running() -> dict | None:
    st = _state()
    if not st:
        return None
    try:
        return st if _ask(st, '/ping', {}, 3).get('ok') else None
    except OSError:
        return None


def serve() -> int:
    """The background oracle: load the model, then answer on 127.0.0.1 until --stop or idle."""
    tropa.load()
    secret = secrets.token_hex(16)
    last = [time.monotonic()]

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_POST(self):
            if self.headers.get('X-Oracle-Secret') != secret:
                self.send_error(403)
                return
            body = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))) or b'{}')
            last[0] = time.monotonic()
            if self.path == '/score':
                try:
                    out = {'results': [tropa.score(t) for t in body['texts']]}  # tropa.score serializes callers
                except (ValueError, RuntimeError) as e:
                    out = {'error': str(e)}
            elif self.path == '/stop':
                out = {'ok': True}
                server.shutdown_after = True
            else:
                out = {'ok': True}
            data = json.dumps(out).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            last[0] = time.monotonic()

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    server.shutdown_after = False
    STATE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE.with_suffix('.tmp')
    tmp.write_text(json.dumps({'port': server.server_address[1], 'secret': secret, 'pid': os.getpid()}))
    os.chmod(tmp, 0o600)
    tmp.replace(STATE)
    server.timeout = 5
    try:
        while not server.shutdown_after and time.monotonic() - last[0] < IDLE_SECONDS:
            server.handle_request()
    finally:
        st = _state()
        if st and st.get('pid') == os.getpid():
            STATE.unlink(missing_ok=True)
    return 0


def keep_alive() -> int:
    if _running():
        print('oracle: already running')
        return 0
    if not tropa.available():
        sys.exit('oracle: needs torch and transformers: pip install -r requirements-model.txt (or use the hosted API)')
    STATE.unlink(missing_ok=True)
    detach = {'creationflags': 0x00000008 | 0x00000200} if os.name == 'nt' else {'start_new_session': True}
    log = STATE.parent / 'oracle.log'
    log.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), '--serve'], stdin=subprocess.DEVNULL,
                            stdout=log.open('w'), stderr=subprocess.STDOUT, **detach)
    deadline = time.monotonic() + START_SECONDS
    while time.monotonic() < deadline:
        if _running():
            print('oracle: running; stop it with --stop')
            return 0
        if proc.poll() is not None:
            sys.exit(f'oracle: the background oracle failed to start; see {log}')
        time.sleep(1)
    proc.terminate()
    sys.exit(f'oracle: not ready after {START_SECONDS} s; see {log}')


def stop() -> int:
    st = _running()
    if not st:
        STATE.unlink(missing_ok=True)
        print('oracle: not running')
        return 0
    try:
        _ask(st, '/stop', {}, 10)
    except OSError:
        pass
    print('oracle: stopped')
    return 0


def main(argv: list[str]) -> int:
    if argv == ['--serve']:
        return serve()
    if argv == ['--keep-alive']:
        return keep_alive()
    if argv == ['--stop']:
        return stop()
    as_json = '--json' in argv
    files = [a for a in argv if a != '--json']
    if not files or any(f.startswith('--') for f in files):
        sys.exit('usage: python3 oracle.py FILE... [--json] | --keep-alive | --stop')
    try:
        texts = [sys.stdin.read() if f == '-' else Path(f).read_text(encoding='utf-8') for f in files]
    except OSError as e:
        sys.exit(f'oracle: {e}')
    st = _running()
    try:
        if st:
            r = _ask(st, '/score', {'texts': texts}, 3600)
            if 'error' in r:
                raise ValueError(r['error'])
            results = r['results']
        else:
            results = [tropa.score(t) for t in texts]
    except (RuntimeError, ValueError, OSError) as e:
        sys.exit(f'oracle: {e}')
    out = dict(zip(files, results))
    if as_json:
        print(json.dumps(out if len(files) > 1 else out[files[0]], indent=1))
    elif len(files) == 1:
        print(tropa.evidence(out[files[0]]))
    else:
        for f, r in out.items():
            top = max(r['labels'], key=r['labels'].get)
            print(f"{f}\tai {r['ai']:.3f}\t{top}{'' if tropa.is_ai(r) else ' (passes)'}")
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
