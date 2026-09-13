"""Approved JR STATS portrait layout, shared across kits and competitions."""
import base64
import io
import math
from html import escape
from pathlib import Path
from PIL import Image, ImageOps, ImageChops
import portrait_graphics as p
import goal_graphics as g

PHASES = {'HT': 'half', '2H_END': 'end_of_90', 'FT': 'full'}
ORDER = ('POSSESSO', 'xG', 'TIRI', 'TIRI IN PORTA', 'CORNER', 'FALLI',
         'FUORIGIOCO', 'AMMONITI', 'ESPULSI', 'PARATE', 'PRECISIONE PASSAGGI', 'PASSAGGI')


def uri(image):
    stream = io.BytesIO()
    image.save(stream, format='PNG')
    return 'data:image/png;base64,' + base64.b64encode(stream.getvalue()).decode()


def rows_html(rows):
    result = []
    for label, home, away in rows:
        try:
            h, a = (float(str(v).replace('%', '').replace(',', '.')) for v in (home, away))
            if not all(math.isfinite(v) and v >= 0 for v in (h, a)):
                continue
        except (ValueError, TypeError):
            continue
        total = h + a
        # True zero is a full-width neutral track; missing data is omitted.
        bars = '' if total == 0 else (
            f'<i style="flex:{h}"></i><b style="flex:{a}"></b>' if h and a else
            '<i style="flex:1"></i>' if h else '<b style="flex:1"></b>')
        result.append(f'<div class="row"><span class="home">{escape(str(home))}</span>'
                      f'<div class="middle"><div class="label">{escape(label)}</div>'
                      f'<div class="track{" empty" if total == 0 else ""}">{bars}</div></div>'
                      f'<span class="away">{escape(str(away))}</span></div>')
    return ''.join(result)


def textured_logo(source, key, assets, silhouette=False):
    mark = p.tight(source)
    mark = mark.resize((round(mark.width * 128 / mark.height), 128), Image.Resampling.LANCZOS)
    result = p.textured(mark, key, assets, zoom=True)
    # Coloured Diretta crests can have an opaque shield/circle. Preserve their
    # internal light/dark drawing rather than turning the whole crest into a disk.
    gray = ImageOps.grayscale(mark)
    visible = [v for v, a in zip(gray.getdata(), mark.getchannel('A').getdata()) if a > 200]
    if not silhouette and visible and max(visible) - min(visible) > 80:
        detail = gray.point(lambda value: max(0, min(255, round((value - 35) * 255 / 180))))
        result.putalpha(ImageChops.multiply(detail, mark.getchannel('A')))
    return result


def build_html(*, rows, kit, competition, league_name, momento, home_id, away_id,
               home_logo, away_logo, assets=g.DEFAULT_ASSET_DIR):
    if '111' not in (str(home_id), str(away_id)):
        raise ValueError('STATS solo Juventus')
    assets = Path(assets)
    key = p.theme(kit, competition)
    bg = Image.open(assets / 'portrait' / f'{key}_clean_1086x1448.png').convert('RGBA')
    if key == 'ucl':
        bg = p.vivid_background(bg)
    bg = uri(p.brand(bg, key, assets))
    title = uri(Image.open(assets / 'portrait' / f'stats_{key}.png'))
    word = p.tight(Image.open(assets / 'portrait' / f'{PHASES[momento]}.png'), True)
    word = word.resize((300, round(word.height * 300 / word.width)), Image.Resampling.LANCZOS)
    phase = uri(p.textured(word, key, assets))
    logos = []
    for source, tid in ((home_logo, home_id), (away_logo, away_id)):
        logos.append(uri(textured_logo(source, key, assets, silhouette=str(tid) == '111')))
    font = 'data:font/otf;base64,' + base64.b64encode((assets / 'fonts/DharmaGothicEBold.otf').read_bytes()).decode()
    left, right = (p.COLORS[key], '#fff') if str(home_id) == '111' else ('#fff', p.COLORS[key])
    template = Path(__file__).with_name('stats.html').read_text(encoding='utf-8')
    values = dict(FONT=font, BACKGROUND=bg, TITLE=title, PHASE=phase, HOME_LOGO=logos[0],
                  AWAY_LOGO=logos[1], LEFT=left, RIGHT=right, ROWS=rows_html(rows),
                  COMPETITION=escape(league_name.upper()))
    for name, value in values.items():
        template = template.replace('{{' + name + '}}', value)
    return template


def render(html, hd_output=True):
    import tempfile
    from playwright.sync_api import sync_playwright
    output = Path(tempfile.mkdtemp(prefix='jr_stats_'))
    source = output / 'stats.html'
    source.write_text(html, encoding='utf-8')
    target = output / 'stats.png'
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={'width': p.W, 'height': p.H},
                                    device_scale_factor=2 if hd_output else 1)
            page.goto(source.as_uri())
            page.evaluate('() => document.fonts.ready')
            page.screenshot(path=str(target))
        finally:
            browser.close()
    if hd_output:
        with Image.open(target) as image:
            image.resize((1920, 2560), Image.Resampling.LANCZOS).save(target)
    return str(target)
