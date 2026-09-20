"""Real exports only: no Telegram, snapshots, live polling or rendering changes."""
import json
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import juve_bot_espn as bot
from canva_page_one import export_page_one


def main():
    original = bot.SESSION.request
    results = []

    def traced(method, url, **kwargs):
        parsed = urlsplit(url)
        if parsed.hostname == 'api.telegram.org':
            raise RuntimeError('Telegram forbidden in diagnostic')
        stage = ('TOKEN' if parsed.path.endswith('/oauth/token') else
                 'CREATE_EXPORT' if method.upper() == 'POST' and parsed.path.endswith('/exports') else
                 'POLL_EXPORT' if '/exports/' in parsed.path else
                 'GITHUB_SECRET' if parsed.hostname == 'api.github.com' else 'PDF_DOWNLOAD')
        started = time.monotonic()
        print(f'BEGIN {stage} timeout={kwargs.get("timeout")}', flush=True)
        try:
            response = original(method, url, **kwargs)
        except Exception as exc:
            # Never print signed URLs, response bodies or credential-bearing exceptions.
            print(f'FAIL {stage} {type(exc).__name__} elapsed={time.monotonic()-started:.2f}s', flush=True)
            raise
        print(f'END {stage} HTTP={response.status_code} elapsed={time.monotonic()-started:.2f}s', flush=True)
        return response

    bot.SESSION.request = traced
    save_secret = bot.update_github_secret

    def persist(name, value):
        for attempt in range(3):
            if save_secret(name, value):
                return True
        raise RuntimeError('Rotated token could not be persisted; stop diagnostic')

    bot.update_github_secret = persist
    for name, pause in [('HT', 0), ('FT_IMMEDIATE', 0), ('END90_AFTER_IDLE', 3860)]:
        if pause:
            print(f'IDLE {pause}s: keeping the same session, no Canva requests', flush=True)
            time.sleep(pause)
        started = time.monotonic()
        try:
            token = bot.get_valid_token()
            if not token:
                raise RuntimeError('Token unavailable: stopping test')
            folder = export_page_one(bot.SESSION, token, bot.CANVA_DESIGN_ID, Path('diagnostic-output'))
            result = dict(phase=name, success=True, pdf_bytes=(folder/'source.pdf').stat().st_size)
        except Exception as exc:
            result = dict(phase=name, success=False, error=type(exc).__name__)
            if not bot._CANVA_ACCESS_TOKEN:
                results.append(result)
                break
        result['seconds'] = round(time.monotonic()-started, 2)
        results.append(result)
        print(json.dumps(result), flush=True)
    Path('diagnostic-results.json').write_text(json.dumps(results, indent=2))
    return 0 if len(results) == 3 and all(r['success'] for r in results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
