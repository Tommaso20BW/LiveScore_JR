"""Grafiche dell'Italia (stile "Raggi"): KICK OFF, 2ND HALF, HALF TIME, END OF 90', FULL TIME,
GOAL, SAVED, STATS e STARTING XI.

Tutte disegnate in HTML e fotografate con Playwright (pagina 1086x1448 resa a 1920x2560):
- home: sfondo azzurro sfumato, scritte bianche; away: sfondo bianco, scritte azzurre;
- fasce diagonali tono su tono, luce morbida al centro, riga tricolore in alto e in basso,
  4 stelle (i Mondiali) in alto a sinistra e logo JR in alto a destra, vicini ai bordi;
- bandiere tonde delle due nazionali (asset `flags_round/`) al posto dei nomi; se una
  bandiera manca resta il nome della squadra;
- scritte in Dharma (parole grandi) e Bebas (nomi, etichette).
L'apostrofo (90', 33') si vede ma non conta per centrare la scritta.
"""

from __future__ import annotations

import base64
import html as _html
import io
import os
import tempfile
from functools import lru_cache
from pathlib import Path

from PIL import Image

from livescore.core import team_names
from livescore.graphics import flags
from livescore.graphics import goal as g

W, H = 1086, 1448                 # pagina (pixel CSS), come le altre grafiche portrait
OUT = (1920, 2560)

THEMES = {
    'ita_home': dict(bg='linear-gradient(160deg,#2b71d2,#1550a8 55%,#0c3577)', ink='#ffffff',
                     sub='rgba(255,255,255,.72)', bar2='rgba(255,255,255,.35)', pitch='rgba(255,255,255,.08)',
                     line='rgba(255,255,255,.85)', lbg='#ffffff', ltx='#1550a8', ring='#ffffff',
                     glow='rgba(255,255,255,.16)', ray='rgba(255,255,255,.035)'),
    'ita_away': dict(bg='linear-gradient(160deg,#ffffff,#e9f0fa)', ink='#1550a8',
                     sub='#6a87b8', bar2='rgba(21,80,168,.25)', pitch='rgba(21,80,168,.06)',
                     line='#1550a8', lbg='#1550a8', ltx='#ffffff', ring='#1550a8',
                     glow='rgba(43,113,210,.10)', ray='rgba(21,80,168,.035)'),
}
TRI = 'linear-gradient(90deg,#009246 0 33.3%,#ffffff 33.3% 66.6%,#ce2b37 66.6%)'
WORDS = {'kick': ('KICK', 'OFF'), 'second': ('2ND', 'HALF'), 'half': ('HALF', 'TIME'),
         'end_of_90': ('END', "OF 90'"), 'full': ('FULL', 'TIME')}
MOMENTS = {'HT': 'HALF TIME', '2H_END': "END OF 90'", 'FT': 'FULL TIME'}


# ------------------------------------------------------------------------------ pezzi comuni
def _esc(text) -> str:
    return _html.escape(str(text))


def _q(text) -> str:
    """Testo con l'apostrofo fuori dal calcolo del centro (larghezza zero, ma visibile)."""
    return _esc(text).replace('&#x27;', "'").replace("'", '<span style="display:inline-block;width:0">\'</span>')


@lru_cache(maxsize=None)
def _file_uri(path: str) -> str:
    path = Path(path)
    mime = {'.otf': 'font/otf', '.ttf': 'font/ttf', '.png': 'image/png'}[path.suffix.lower()]
    return f'data:{mime};base64,' + base64.b64encode(path.read_bytes()).decode()


def _team(name: str) -> str:
    return team_names.translate_team(name).upper()


def _flag(name: str, size: int, t: dict, assets: Path) -> str:
    path = flags.path_for(name, assets)
    if path is None:                                   # bandiera mancante: il nome della squadra
        return (f'<span style="font-family:Bebas;font-size:{round(size * .62)}px;line-height:1;color:{t["ink"]};'
                f'letter-spacing:.03em">{_esc(_team(name))}</span>')
    return (f'<img src="{_file_uri(str(path))}" style="width:{size}px;height:{size}px;border-radius:50%;'
            f'box-shadow:0 0 0 {size * .045:.1f}px {t["ring"]}">')


def _score_row(home, away, score, t, assets, size=86, font=96, gap=28):
    mid = (f'<span style="font-family:Dharma;font-size:{font}px;line-height:1;color:{t["ink"]};margin:0 {gap}px">'
           f'{score[0]}-{score[1]}</span>' if score else f'<span style="width:{gap * 2}px"></span>')
    return (f'<div style="display:flex;align-items:center;justify-content:center">'
            f'{_flag(home, size, t, assets)}{mid}{_flag(away, size, t, assets)}</div>')


def _page(kit, body, assets, *, stars=True) -> str:
    t = THEMES[kit]
    fonts = assets / 'fonts'
    jr = _file_uri(str(assets / 'overlays' / 'jr.png'))
    # In alto a sinistra: le 4 stelle dei Mondiali vinti dall'Italia.
    star = (f'<svg width="30" height="30" viewBox="0 0 24 24"><path fill="{t["ink"]}" '
            f'd="M12 1.8l3.1 6.6 7.2.9-5.3 5 1.4 7.1L12 17.9l-6.4 3.5 1.4-7.1-5.3-5 7.2-.9z"/></svg>')
    top = (f'<div class="ab" style="left:28px;top:44px;display:flex;gap:10px">{star * 4}</div>'
           if stars else '')
    return f'''<!doctype html><html><head><meta charset="utf-8"><style>
@font-face{{font-family:Dharma;src:url({_file_uri(str(fonts / 'DharmaGothicEBold.otf'))})}}
@font-face{{font-family:Bebas;src:url({_file_uri(str(fonts / 'BebasNeue2014-Regular.ttf'))})}}
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{width:{W}px;height:{H}px;overflow:hidden;background:{t['bg']};position:relative}}
.ab{{position:absolute}}
.lab{{font-family:Bebas;letter-spacing:.06em;white-space:nowrap}}
.word{{font-family:Dharma;line-height:.84;white-space:nowrap;color:{t['ink']};display:inline-block}}
</style></head><body>
<div class="ab" style="inset:0;background:repeating-linear-gradient(118deg,transparent 0 150px,{t['ray']} 150px 300px)"></div>
<div class="ab" style="inset:0;background:radial-gradient(ellipse 70% 45% at 50% 42%,{t['glow']},transparent 70%)"></div>
<div class="ab" style="left:0;right:0;top:0;height:14px;background:{TRI}"></div>
<div class="ab" style="left:0;right:0;bottom:0;height:14px;background:{TRI}"></div>
<div class="ab" style="right:22px;top:34px;width:63px;height:84px;background:{t['ink']};
  -webkit-mask:url({jr}) center/contain no-repeat;mask:url({jr}) center/contain no-repeat"></div>
{top}{body}
<script>
// parole troppo larghe: si rimpiccioliscono finché stanno nello spazio indicato
window.__fit = document.fonts.ready.then(() => document.querySelectorAll('[data-fit]').forEach(el => {{
  const max = +el.dataset.fit; let s = parseFloat(getComputedStyle(el).fontSize);
  while (el.scrollWidth > max && s > 20) {{ s -= 2; el.style.fontSize = s + 'px'; }}
}}));
</script></body></html>'''


# ------------------------------------------------------------------------------ grafiche
def phase_html(*, kind, kit, home_name, away_name, home_goals=0, away_goals=0, competition='',
               caption=None, assets=g.DEFAULT_ASSET_DIR) -> str:
    assets = Path(assets)
    t = THEMES[kit]
    l1, l2 = WORDS[kind]
    score = None if kind == 'kick' else (home_goals, away_goals)
    cap = (f'<div class="ab" style="left:0;right:0;top:1150px;text-align:center"><div class="lab" style="display:inline-block;'
           f'font-size:50px;color:{t["ink"]}" data-fit="900">{_esc(caption)}</div></div>' if caption else '')
    body = f'''
<div class="ab" style="left:0;right:0;top:420px">{_score_row(home_name, away_name, score, t, assets)}</div>
<div class="ab" style="left:0;right:0;top:560px;text-align:center">
  <div class="word" style="font-size:300px" data-fit="900"><div>{_q(l1)}</div><div>{_q(l2)}</div></div></div>
{cap}'''
    return _page(kit, body, assets)


def event_html(*, kit, saved, player_name, minute, home_name, away_name, home_goals=None, away_goals=None,
               competition='', assets=g.DEFAULT_ASSET_DIR) -> str:
    assets = Path(assets)
    t = THEMES[kit]
    word = 'SAVED' if saved else 'GOAL'
    minute = str(minute or '').strip().rstrip("'’")
    score = (home_goals, away_goals) if home_goals is not None and away_goals is not None else None
    body = f'''
<div class="ab" style="left:0;right:0;top:430px;text-align:center"><div class="word" style="font-size:440px" data-fit="940">{word}</div></div>
<div class="ab" style="left:0;right:0;top:850px;text-align:center">
  <div class="lab" style="display:inline-block;font-size:100px;line-height:1;letter-spacing:.03em;color:{t['ink']}" data-fit="920">{_esc(player_name.upper())}</div></div>
<div class="ab lab" style="left:0;right:0;top:965px;text-align:center;font-size:46px;color:{t['sub']}">{_q(minute + "'") if minute else ''}</div>
<div class="ab" style="left:0;right:0;top:1110px">{_score_row(home_name, away_name, score, t, assets, 80, 90)}</div>'''
    return _page(kit, body, assets)


def _number(value) -> float | None:
    try:
        v = float(str(value).replace('%', '').replace(',', '.'))
    except (TypeError, ValueError):
        return None
    return v if v >= 0 else None


def stats_html(*, kit, rows, momento, home_name, away_name, competition='', assets=g.DEFAULT_ASSET_DIR) -> str:
    assets = Path(assets)
    t = THEMES[kit]
    rows = [(lab, h, a) for lab, h, a in rows if _number(h) is not None and _number(a) is not None]
    # Etichetta sempre al centro della pagina (colonne 1fr auto 1fr), qualunque sia la
    # larghezza dei due numeri.
    # Righe distribuite su tutta la parte sotto il titolo (365-1375 px), centrate in verticale.
    # Numeri e scritte crescono con lo spazio della riga: di solito 11-12 statistiche,
    # con 12 numeri ~72 px e scritte ~40 px.
    step = min(260, 1010 / max(1, len(rows)))
    big = min(150, step * .86)
    top0 = 365 + (1010 - step * len(rows)) / 2
    out = ''
    for i, (lab, h, a) in enumerate(rows):
        hv, av = _number(h), _number(a)
        share = .5 if hv + av == 0 else hv / (hv + av)
        out += f'''
<div class="ab" style="left:110px;right:110px;top:{top0 + i * step:.0f}px">
  <div style="display:grid;grid-template-columns:1fr auto 1fr;align-items:end">
    <span style="justify-self:start;font-family:Dharma;font-size:{big:.0f}px;line-height:.9;color:{t['ink']}">{_esc(h)}</span>
    <span class="lab" style="font-size:{min(58, big * .56):.0f}px;padding-bottom:{big * .08:.0f}px;color:{t['sub']}">{_esc(lab)}</span>
    <span style="justify-self:end;font-family:Dharma;font-size:{big:.0f}px;line-height:.9;color:{t['ink']}">{_esc(a)}</span></div>
  <div style="display:flex;height:{min(22, step * .12):.0f}px;margin-top:{min(16, step * .04):.0f}px;gap:10px">
    <div style="flex:{share:.6f};background:{t['ink']}"></div><div style="flex:{1 - share:.6f};background:{t['bar2']}"></div></div>
</div>'''
    body = f'''
<div class="ab" style="left:0;right:0;top:95px;text-align:center"><div class="word" style="font-size:200px">STATS</div></div>
<div class="ab lab" style="left:0;right:0;top:282px;text-align:center;font-size:40px;color:{t['sub']}">{_q(MOMENTS.get(momento, ''))}</div>
<div class="ab" style="left:110px;top:130px">{_flag(home_name, 110, t, assets)}</div>
<div class="ab" style="right:110px;top:130px">{_flag(away_name, 110, t, assets)}</div>
{out}'''
    return _page(kit, body, assets)


def xi_html(*, kit, lines, home_name, away_name, assets=g.DEFAULT_ASSET_DIR) -> str:
    """`lines`: cognomi per linea, dal portiere all'attacco (es. [['DONNARUMMA'], [4 nomi], ...])."""
    assets = Path(assets)
    t = THEMES[kit]
    px, py, pw, ph = 110, 230, W - 220, 1150
    labels = ''
    n = len(lines)
    for i, row in enumerate(lines):
        y = py + ph - 95 - i * (ph - 190) / max(1, n - 1)
        x0, w = (40, W - 80) if len(row) >= 4 else (px + 10, pw - 20)
        for j, name in enumerate(row):
            room = w / len(row) - 14
            labels += (f'<div class="lb" style="left:{x0 + w * (j + .5) / len(row):.0f}px;top:{y:.0f}px" '
                       f'data-fit="{room:.0f}">{_esc(name)}</div>')
    cx, my = pw / 2, ph / 2
    bw, bh, gw, gh, r = pw * .5, ph * .16, pw * .27, ph * .065, pw * .14
    ln = t['line']
    pitch = (f'<svg class="ab" style="left:{px}px;top:{py}px" width="{pw}" height="{ph}">'
             f'<rect x="3" y="3" width="{pw - 6}" height="{ph - 6}" rx="8" fill="{t["pitch"]}" stroke="{ln}" stroke-width="5"/>'
             f'<g fill="none" stroke="{ln}" stroke-width="4"><line x1="3" y1="{my}" x2="{pw - 3}" y2="{my}"/>'
             f'<circle cx="{cx}" cy="{my}" r="{r}"/><rect x="{cx - bw / 2}" y="3" width="{bw}" height="{bh}"/>'
             f'<rect x="{cx - gw / 2}" y="3" width="{gw}" height="{gh}"/>'
             f'<rect x="{cx - bw / 2}" y="{ph - 3 - bh}" width="{bw}" height="{bh}"/>'
             f'<rect x="{cx - gw / 2}" y="{ph - 3 - gh}" width="{gw}" height="{gh}"/></g></svg>')
    body = f'''
<style>.lb{{position:absolute;transform:translate(-50%,-50%);padding:14px 22px 10px;background:{t['lbg']};color:{t['ltx']};
  font-family:Bebas;font-size:40px;letter-spacing:.04em;white-space:nowrap}}</style>
<div class="ab" style="left:0;right:0;top:62px;display:flex;align-items:center;justify-content:center;gap:30px">
  {_flag(home_name, 96, t, assets)}<div class="word" style="font-size:120px;line-height:1;padding-top:6px">STARTING XI</div>{_flag(away_name, 96, t, assets)}</div>
{pitch}{labels}'''
    return _page(kit, body, assets)


# ------------------------------------------------------------------------------ resa
def render(html: str) -> bytes:
    """PNG 1920x2560 della pagina."""
    from playwright.sync_api import sync_playwright

    folder = Path(tempfile.mkdtemp(prefix='jr_italy_'))
    source, target = folder / 'page.html', folder / 'page.png'
    source.write_text(html, encoding='utf-8')
    try:
        with sync_playwright() as playwright:
            # ImageGen su GitHub usa il Chrome di sistema (IMAGEGEN_CHROME); altrove il Chromium di Playwright.
            browser = playwright.chromium.launch(executable_path=os.environ.get('IMAGEGEN_CHROME') or None)
            try:
                page = browser.new_page(viewport={'width': W, 'height': H}, device_scale_factor=2)
                page.goto(source.as_uri())
                page.evaluate('() => window.__fit')
                page.screenshot(path=str(target))
            finally:
                browser.close()
        with Image.open(target) as image:
            out = io.BytesIO()
            # Niente optimize=True: su 1920x2560 costa ~6 s per risparmiare il 6% del file.
            image.convert('RGB').resize(OUT, Image.Resampling.LANCZOS).save(out, format='PNG')
            return out.getvalue()
    finally:
        for f in folder.iterdir():
            f.unlink()
        folder.rmdir()
