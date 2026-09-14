"""Approved JR STATS portrait layout, shared across kits and competitions."""
import base64
import io
import math
from html import escape
from pathlib import Path
from PIL import Image
import portrait_graphics as p
import goal_graphics as g

PHASES = {'HT': 'half', '2H_END': 'end_of_90', 'FT': 'full'}
ORDER = ('POSSESSO', 'xG', 'TIRI', 'TIRI IN PORTA', 'CORNER', 'FALLI',
         'FUORIGIOCO', 'AMMONITI', 'ESPULSI', 'PARATE', 'PRECISIONE PASSAGGI', 'PASSAGGI')

# Nome breve/editoriale mostrato SOLO nel footer delle grafiche STATS.
# Il resto del bot continua a usare senza modifiche il nome originale ESPN.
COMPETITION_DISPLAY_NAMES = {
    'ita.1': 'Serie A',
    'ita.coppa_italia': 'Coppa Italia',
    'ita.super_cup': 'Supercoppa Italiana',

    'uefa.champions': 'Champions League',
    'uefa.champions_qual': 'Champions League',
    'uefa.europa': 'Europa League',
    'uefa.europa_qual': 'Europa League',
    'uefa.europa.conf': 'Conference League',
    'uefa.europa.conf_qual': 'Conference League',
    'uefa.europa_conf': 'Conference League',
    'uefa.super_cup': 'Supercoppa UEFA',

    'fifa.cwc': 'Mondiale per Club',
    'fifa.intercontinental_cup': 'Coppa Intercontinentale',

    # Le amichevoli normalmente non generano STATS, ma restano mappate
    # come fallback nel caso vengano abilitate in futuro.
    'club.friendly': 'Amichevole',
    'friendly.club': 'Amichevole',
    'fifa.friendly': 'Amichevole',
}


def competition_display_name(competition, league_name):
    """Nome da mostrare nella grafica, senza alterare i dati ESPN del bot."""
    slug = str(competition or '').strip()
    return COMPETITION_DISPLAY_NAMES.get(
        slug,
        str(league_name or slug or 'Competizione')
    )


def uri(image):
    stream = io.BytesIO()
    image.save(stream, format='PNG')
    return 'data:image/png;base64,' + base64.b64encode(stream.getvalue()).decode()


def rows_html(rows):
    result = []

    for label, home, away in rows:
        try:
            h, a = (
                float(str(v).replace('%', '').replace(',', '.'))
                for v in (home, away)
            )
            if not all(math.isfinite(v) and v >= 0 for v in (h, a)):
                continue
        except (ValueError, TypeError):
            continue

        total = h + a

        # IMPORTANT:
        # Con valori inferiori a 1 (es. xG 0.30 vs 0.13), usare direttamente
        # flex:0.30 e flex:0.13 lascia una parte della track vuota, perché la
        # somma dei flex-grow è < 1.
        #
        # Normalizziamo quindi SEMPRE le due quote sul totale. In questo modo
        # la barra occupa il 100% della larghezza disponibile mantenendo la
        # proporzione corretta per qualunque statistica.
        if total == 0:
            bars = ''
        elif h > 0 and a > 0:
            h_share = h / total
            a_share = a / total
            bars = (
                f'<i style="flex:{h_share:.10f}"></i>'
                f'<b style="flex:{a_share:.10f}"></b>'
            )
        elif h > 0:
            bars = '<i style="flex:1"></i>'
        else:
            bars = '<b style="flex:1"></b>'

        result.append(
            f'<div class="row">'
            f'<span class="home">{escape(str(home))}</span>'
            f'<div class="middle">'
            f'<div class="label">{escape(label)}</div>'
            f'<div class="track{" empty" if total == 0 else ""}">{bars}</div>'
            f'</div>'
            f'<span class="away">{escape(str(away))}</span>'
            f'</div>'
        )

    return ''.join(result)


def build_html(*, rows, kit, competition, league_name, momento, home_id, away_id,
               home_name, away_name, assets=g.DEFAULT_ASSET_DIR):
    if '111' not in (str(home_id), str(away_id)):
        raise ValueError('STATS solo Juventus')

    assets = Path(assets)
    key = p.theme(kit, competition)

    bg = Image.open(
        assets / 'portrait' / f'{key}_clean_1086x1448.png'
    ).convert('RGBA')

    if key == 'ucl':
        bg = p.vivid_background(bg)

    bg = uri(p.brand(bg, key, assets))
    title = uri(Image.open(assets / 'portrait' / f'stats_{key}.png'))

    word = p.tight(
        Image.open(assets / 'portrait' / f'{PHASES[momento]}.png'),
        True
    )
    word = word.resize(
        (300, round(word.height * 300 / word.width)),
        Image.Resampling.LANCZOS
    )
    phase = uri(p.textured(word, key, assets))

    logos = []
    for name, tid in ((home_name, home_id), (away_name, away_id)):
        # Exactly the same resolver, alpha and zoomed texture as event/phase cards.
        mark = p.logo(name, tid, key, assets, 128)
        if mark is None:
            raise g.GoalGraphicUnavailable(f'Logo non disponibile: {name}')
        logos.append(uri(mark))

    font = (
        'data:font/otf;base64,'
        + base64.b64encode(
            (assets / 'fonts/DharmaGothicEBold.otf').read_bytes()
        ).decode()
    )

    left, right = (
        (p.COLORS[key], '#fff')
        if str(home_id) == '111'
        else ('#fff', p.COLORS[key])
    )

    template = Path(__file__).with_name('stats.html').read_text(encoding='utf-8')

    values = dict(
        FONT=font,
        BACKGROUND=bg,
        TITLE=title,
        PHASE=phase,
        HOME_LOGO=logos[0],
        AWAY_LOGO=logos[1],
        LEFT=left,
        RIGHT=right,
        ROWS=rows_html(rows),
        COMPETITION=escape(
            competition_display_name(competition, league_name).upper()
        )
    )

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
            page = browser.new_page(
                viewport={'width': p.W, 'height': p.H},
                device_scale_factor=2 if hd_output else 1
            )
            page.goto(source.as_uri())
            page.evaluate('() => document.fonts.ready')
            page.screenshot(path=str(target))
        finally:
            browser.close()

    if hd_output:
        with Image.open(target) as image:
            image.resize(
                (1920, 2560),
                Image.Resampling.LANCZOS
            ).save(target)

    return str(target)
