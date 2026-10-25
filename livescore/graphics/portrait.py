"""Approved 3:4 compositor. No generation, Canva edits, or Telegram side effects."""
import io
import math
import random
from pathlib import Path
from PIL import Image, ImageDraw, ImageOps, ImageFont, ImageColor, ImageStat, ImageFilter, ImageMath, ImageEnhance
from livescore.graphics import goal as g
from livescore.core import team_names

W, H, M = 1086, 1448, 76
IW, IH = W - 2 * M, H - 2 * M
# Lowers the front word, crests and name on GOAL/SAVED cards (the big heading stays put).
BOTTOM_SHIFT = 50
# Top row under the heading: score on the left and minute on the right when True.
SCORE_LEFT = True

# Lettering / minute / name colour per theme (texture tint).
AWAY_DARK = '#2B2B2B'   # black items on the pink Away panel

COLORS = dict(
    home='#F4C430',
    away='#EE9AB8',
    third='#C2A564',
    ucl='#63D8FF',
    uel='#FA7A22',
    conference='#30C033',
)
# Shadow tint behind words and crests: each panel's deep tone instead of plain black.
SHADOW = dict(
    home='#000000',
    away='#1A0710',
    third='#120D04',
    ucl='#08061E',
    uel='#140800',
    conference='#011207',
)
# UCL lettering: electric blue -> light azure, random direction every render.
UCL_GRADIENT = ('#3A5BFF', '#3D8BFF', '#55B8FF')
# JR mark: same family, softer magenta end.
UCL_MARK_GRADIENT = ('#3A5BFF', '#3D8BFF', '#55B8FF')
# Small UCL texts (score, minute, name, phase score, shootout, STATS numbers): same softer palette, with texture.
UCL_TEXT_GRADIENT = ('#3A5BFF', '#3D8BFF', '#55B8FF')

# Final dimensions/positions taken from the local preview tests:
# - score numbers: 300 instead of 200
# - phase crests: 43% of score height
# - score/crest group: lifted by 65 px
# - shootout caption: lifted from 1320 to 1285
PHASE_SCORE_FONT_SIZE = 300
PHASE_LOGO_HEIGHT_FACTOR = 0.43
PHASE_GROUP_LIFT = 65
PHASE_PENALTY_CAPTION_Y = 1285


def theme(kit='home', competition='', saved=False):
    value = competition.lower()
    if 'conference' in value or 'europa.conf' in value or 'europa_conf' in value:
        return 'conference'
    if 'champions' in value:
        return 'ucl'
    if 'europa' in value:
        return 'uel'
    return kit if kit in ('home', 'away', 'third') else 'home'


def texture_key(key):
    return key if key in ('home', 'away', 'third') else 'home'


def tight(source, white_mask=False):
    source = source.convert('RGBA')
    alpha = source.getchannel('A')
    if white_mask and alpha.getextrema() == (255, 255):
        alpha = ImageOps.grayscale(source)
    source.putalpha(alpha)
    box = alpha.point(lambda a: 255 if a > 100 else 0).getbbox()
    if not box:
        raise ValueError('Asset vuoto')
    return source.crop(box)


def anchored_player(source, target_height=1450):
    """Ritaglia il PNG del giocatore senza perdere il centro originale del canvas.

    Prima il compositor usava ``tight(raw)`` e poi centrava geometricamente il
    bounding box visibile. Con pose asimmetriche (es. braccio/dito verso sinistra)
    il bounding box non ha lo stesso centro del canvas sorgente: il giocatore
    finiva quindi spostato anche se il PNG di partenza era gia centrato bene.

    Qui continuiamo a rimuovere lo spazio trasparente per mantenere la stessa
    scala verticale, ma conserviamo come ancora orizzontale il centro X del
    canvas originale.
    """
    source = source.convert('RGBA')
    alpha = source.getchannel('A')
    box = alpha.point(lambda a: 255 if a > 100 else 0).getbbox()
    if not box:
        raise ValueError('Asset giocatore vuoto')

    cropped = source.crop(box)
    if cropped.height <= 0:
        raise ValueError('Altezza giocatore non valida')

    scale = target_height / cropped.height
    width = max(1, round(cropped.width * scale))
    portrait = cropped.resize((width, target_height), Image.Resampling.LANCZOS)

    # Posizione, dentro il crop, del centro X del canvas sorgente.
    # Sarà questa coordinata ad essere allineata al centro della card.
    anchor_x = (source.width / 2 - box[0]) * scale
    return portrait, anchor_x


def textured(source, key, assets, zoom=False, color=None, bright=False):
    color = color or COLORS[key]
    texture = Image.open(assets / 'word_textures' / f'{texture_key(key)}.png')
    if not zoom:
        return g._tint_textured_overlay(source, color, texture, preserve_source_detail=False)

    texture = ImageOps.autocontrast(texture.convert('L'), cutoff=1)
    w, h = texture.size
    if bright:
        patches = [
            texture.crop((x * w // 8, y * h // 8, x * w // 8 + w // 4, y * h // 8 + h // 4))
            for x in range(7) for y in range(7)
        ]
        texture = max(patches, key=lambda im: ImageStat.Stat(im).mean[0])
    else:
        texture = texture.crop((w * 3 // 8, h * 3 // 8, w * 5 // 8, h * 5 // 8))

    texture = ImageOps.fit(texture, source.size, method=Image.Resampling.LANCZOS)

    if key == 'third':
        # Restore detail lost by the enlarged crop without adding more folds.
        texture = ImageEnhance.Contrast(texture).enhance(2.0)

    channels = [
        texture.point(
            lambda v, c=c: round(max(0, min(255, c * (.75 + .4 * v / 255) + (18 * v / 255 if c < 12 else 0))))
        )
        for c in ImageColor.getrgb(color)
    ]
    result = Image.merge('RGB', channels).convert('RGBA')
    result.putalpha(source.getchannel('A'))
    return result


def brand(card, key, assets):
    mark = tight(Image.open(assets / 'overlays/jr.png'))
    height = round(H * 58 / 1280)
    mark = mark.resize((round(mark.width * height / mark.height), height), Image.Resampling.LANCZOS)
    # Near-black (not pure black) so the texture still shows; UCL matches its lettering.
    color = '#63D8FF' if key == 'ucl' else ('#EE9AB8' if key == 'away' else '#2B2B2B')
    # Flat colour, no texture light: the mark stays clean on every frame.
    # UCL: same random gradient as the lettering, but without texture.
    if key == 'ucl':
        mark = ucl_gradient(mark, assets, random.Random(), lit=False, stops=UCL_MARK_GRADIENT)
    else:
        flat = Image.new('RGBA', mark.size, ImageColor.getrgb(color) + (255,))
        flat.putalpha(mark.convert('RGBA').getchannel('A'))
        mark = flat
    x = W - round(W * 16 / 960) - mark.width
    assert x > W - M
    card.alpha_composite(mark, (x, round(H * 13 / 1280)))
    return card


def crest_texture(source, key, assets):
    """Mono crests: kit texture, or the random UCL gradient (with texture) on Champions League."""
    if key == 'ucl':
        return ucl_gradient(source, assets, random.Random())
    return textured(source, key, assets, True)


def flat_color(layer, color):
    """Same shape, one flat colour (None passes through)."""
    if layer is None:
        return None
    out = Image.new('RGBA', layer.size, ImageColor.getrgb(color) + (255,))
    out.putalpha(layer.getchannel('A'))
    return out


def logo(name, tid, key, assets, height):
    source, origin = g.resolve_team_logo_source(name, str(tid), assets)
    if source is None:
        return None
    source = tight(source)
    source = source.resize((round(source.width * height / source.height), height), Image.Resampling.LANCZOS)
    return crest_texture(source, key, assets) if origin == 'FCLogo' else source


def centered_logo_positions(marks, center, gap=20):
    """Center the tight visible bounds as a group, not fixed logo slots."""
    marks = [mark for mark in marks if mark is not None]
    total = sum(mark.width for mark in marks) + max(0, len(marks) - 1) * gap
    x = round(center - total / 2)
    for mark in marks:
        yield mark, x
        x += mark.width + gap


def phase_logo(name, tid, key, assets, height):
    """Load a phase-card crest without cropping its transparent PNG padding."""
    source, origin = g.resolve_team_logo_source(name, str(tid), assets)
    if source is None:
        return None
    source = source.convert('RGBA')
    if source.height <= 0:
        raise ValueError('Altezza logo non valida')
    width = max(1, round(source.width * height / source.height))
    source = source.resize((width, height), Image.Resampling.LANCZOS)
    return crest_texture(source, key, assets) if origin == 'FCLogo' else source


def visible_logo_bbox(mark, threshold=100):
    """Return visible alpha bounds while leaving the padded logo untouched."""
    mark = mark.convert('RGBA')
    box = mark.getchannel('A').point(lambda a: 255 if a > threshold else 0).getbbox()
    if not box:
        raise ValueError('Logo vuoto')
    return box


def phase_group_positions(home_mark, away_mark, score_width, canvas_width=W, gap=28):
    """Anchor the score at card center; space visible crests independently."""
    home_box = visible_logo_bbox(home_mark) if home_mark is not None else None
    away_box = visible_logo_bbox(away_mark) if away_mark is not None else None
    score_x = round((canvas_width - score_width) / 2)
    home_x = score_x - gap - home_box[2] if home_box else None
    away_x = score_x + score_width + gap - away_box[0] if away_box else None
    return score_x, home_x, away_x


def number(text, size, key, assets):
    font = ImageFont.truetype(str(assets / 'fonts/DharmaGothicEBold.otf'), size)
    box = font.getbbox(text)
    layer = Image.new('RGBA', (max(1, box[2] - box[0]), max(1, box[3] - box[1])))
    ImageDraw.Draw(layer).text((-box[0], -box[1]), text, font=font, fill='white')
    if key == 'ucl':
        return ucl_gradient(layer, assets, random.Random(), stops=UCL_TEXT_GRADIENT)
    return textured(layer, key, assets, True)


def png(card):
    stream = io.BytesIO()
    card.convert('RGB').save(stream, format='PNG')
    return stream.getvalue()


# Big lettering behind the player: (file, width, offset inside the panel).
HEADINGS = {
    True: ('front_saved.png', 1072, (-69, -63)),   # cut 69px on both sides, same as GOAL
    False: ('front_goal.png', 1072, (-69, -63)),
}


def event_heading(assets, saved):
    name, width, offset = HEADINGS[saved]
    heading = tight(Image.open(Path(assets) / 'overlays' / name), True)
    # Uniform scaling preserves the supplied lettering's original proportions.
    heading = heading.resize((width, round(heading.height * width / heading.width)), Image.Resampling.LANCZOS)
    layer = Image.new('RGBA', (IW, IH))
    layer.alpha_composite(heading, offset)
    return layer


def saved_heading(assets):
    return event_heading(assets, True)




def event(
    *,
    player,
    scorer_name,
    minute,
    home_name,
    away_name,
    home_id,
    away_id,
    kit,
    saved=False,
    suffix='',
    competition='',
    pose=None,
    event_key='',
    home_goals=None,
    away_goals=None,
    assets=g.DEFAULT_ASSET_DIR,
):
    assets = Path(assets)
    key = theme(kit, competition, saved)
    background = assets / 'portrait' / f'{key}_clean_1086x1448.png'
    card = Image.open(background).convert('RGBA')

    panel = card.crop((M, M, W - M, H - M))
    heading = event_heading(assets, saved)
    seed = random.random()          # one random gradient per card, shared by both words

    def letters(source):
        if key == 'ucl':
            return ucl_gradient(source, assets, random.Random(seed))
        return textured(source, key, assets)

    # Soft shadow under the top heading; drawn on the panel, so it is cut at the panel edges like the word.
    tinted_shadow(panel, heading.getchannel('A'), key, blur=14, opacity=.55, offset=6)
    panel.alpha_composite(textured(heading, key, assets, color=AWAY_DARK) if key == 'away' else letters(heading))

    path = None
    pose = pose or 'arms_crossed'
    if player:
        path = g.resolve_player_path(player, kit, pose, assets)
        if path and Path(path).is_file():
            with Image.open(path) as raw:
                if not g._has_real_transparency(raw):
                    raise g.GoalGraphicUnavailable('PNG giocatore non scontornato')

                # FIX CENTRATURA:
                # non centrare il bounding box della sagoma, ma il centro X
                # originale del PNG. In questo modo le pose con braccio/dito
                # esteso non trascinano tutto il corpo a destra o sinistra.
                portrait, anchor_x = anchored_player(raw, 1450)

            panel_x = round(IW / 2 - anchor_x)
            panel.alpha_composite(portrait, (panel_x, -25))

            # I primi 25 px salgono sopra il pannello interno: manteniamo la
            # stessa identica ancora X anche nella porzione compositata sul card.
            card.alpha_composite(
                portrait.crop((0, 0, portrait.width, 25)),
                (M + panel_x, M - 25),
            )
        else:
            path = None

    fade = Image.new('RGBA', panel.size)
    draw = ImageDraw.Draw(fade)
    for y in range(520, IH):
        draw.line((0, y, IW, y), fill=(0, 0, 0, round(238 * min(1, (y - 520) / (IH - 520)) ** 1.35)))
    panel.alpha_composite(fade)
    card.alpha_composite(panel, (M, M))

    word = tight(Image.open(assets / 'overlays' / ('front_saved.png' if saved else 'front_goal.png')), True)
    word = ImageOps.contain(word, (IW + 44, 340), Image.Resampling.LANCZOS)
    word = letters(word)
    place_word(card, word, saved, key)

    # Minute left and score right, just under the big heading at the top (same on GOAL and SAVED).
    # Everything sits on one baseline; edges are aligned on the drawn ink, not the font advance.
    font = ImageFont.truetype(str(assets / 'fonts/DharmaGothicEBold.otf'), 52)
    cap = -font.getbbox('0', anchor='ls')[1]
    baseline = M + heading.getchannel('A').getbbox()[3] + 30 + cap
    side = 16      # close to the panel edge, never touching it
    draw = ImageDraw.Draw(card)

    def put(parts, align):
        """Draw parts edge to edge on their ink, flush to the left or right panel edge."""
        boxes = [font.getbbox(s, anchor='ls') for s in parts]
        width = sum(b[2] - b[0] for b in boxes)
        x = M + side if align == 'left' else W - M - side - width
        if key == 'ucl':
            # UCL: same random gradient + texture as the words, not flat light blue.
            layer = Image.new('RGBA', card.size)
            ld = ImageDraw.Draw(layer)
            for s, b in zip(parts, boxes):
                ld.text((x - b[0], baseline), s, font=font, fill='white', anchor='ls')
                x += b[2] - b[0]
            area = layer.getchannel('A').getbbox()
            if area:
                piece = ucl_gradient(layer.crop(area), assets, random.Random(seed), stops=UCL_TEXT_GRADIENT)
                card.alpha_composite(piece, area[:2])
            return
        for s, b in zip(parts, boxes):
            draw.text((x - b[0], baseline), s, font=font, fill=AWAY_DARK if key == 'away' else COLORS[key], anchor='ls')
            x += b[2] - b[0]

    minute_parts = [str(minute).rstrip("'’") + "'"]
    score_parts = ([str(home_goals), '-', str(away_goals)]       # "1-0" with no space
                   if home_goals is not None and away_goals is not None else None)
    put(minute_parts, 'right' if SCORE_LEFT else 'left')
    if score_parts:
        put(score_parts, 'left' if SCORE_LEFT else 'right')

    marks = [logo(name, tid, key, assets, 64) for name, tid in [(home_name, home_id), (away_name, away_id)]]
    for mark, x in centered_logo_positions(marks, W / 2):
        soft_place(card, mark, (x, 1180 + BOTTOM_SHIFT - mark.height // 2), blur=6, opacity=.50, key=key)

    label = (scorer_name + suffix).upper()
    size = 29
    while size > 14 and g._font(size).getlength(label) > IW - 40:
        size -= 1
    center_name(card, label, g._font(size), key=key, assets=assets)

    return g.RenderedGoal(
        png(brand(card, key, assets)),
        player if path else None,
        scorer_name,
        'saved' if saved else kit,
        pose,
        path,
        background,
    )


def phase_word(word, key, assets):
    """KICK OFF / HALF TIME / ... word: random gradient on UCL, kit texture elsewhere."""
    if key == 'ucl':
        return ucl_gradient(word, assets, random.Random())
    return textured(word, key, assets)


def phase(
    *,
    kind,
    home_name,
    away_name,
    home_id,
    away_id,
    home_goals=0,
    away_goals=0,
    kit='home',
    competition='',
    layers=None,
    shootout=None,
    assets=g.DEFAULT_ASSET_DIR,
):
    if kind not in ('kick', 'half', 'full', 'end_of_90'):
        raise ValueError('Fase senza grafica')

    assets = Path(assets)
    key = theme(kit, competition)
    card = Image.open(assets / 'portrait' / f'{key}_clean_1086x1448.png').convert('RGBA')

    word = tight(Image.open(assets / 'overlays' / f'{kind}.png'), True)

    if kind == 'kick':
        word = ImageOps.contain(word, (600, 600), Image.Resampling.LANCZOS)
        top = (H - 64 - 38 - word.height) // 2
        kw = textured(word, key, assets, color=AWAY_DARK) if key == 'away' else phase_word(word, key, assets)
        card.alpha_composite(kw, ((W - word.width) // 2, top + 102))
        marks = [logo(name, tid, key, assets, 64) for name, tid in [(home_name, home_id), (away_name, away_id)]]
        if key == 'away':
            marks = [flat_color(m, AWAY_DARK) for m in marks]
        for mark, x in centered_logo_positions(marks, W / 2):
            soft_place(card, mark, (x, top), blur=6, opacity=.50, key=key)
    else:
        if layers is None:
            raise ValueError('Pagina 1 Canva non disponibile')

        # Both extracted layers share the PDF page coordinates and transform.
        bg = ImageOps.fit(
            Image.open(Path(layers) / 'background.png').convert('RGBA'),
            (IW, IH),
            method=Image.Resampling.LANCZOS,
        )
        player = ImageOps.fit(
            Image.open(Path(layers) / 'player.png').convert('RGBA'),
            (IW, IH),
            method=Image.Resampling.LANCZOS,
        )
        word = word.resize((IW - 36, round(word.height * (IW - 36) / word.width)), Image.Resampling.LANCZOS)
        soft_place(bg, phase_word(word, key, assets), (18, 28), blur=12, opacity=.60, key=key)
        bg.alpha_composite(player)

        fade = Image.new('RGBA', bg.size)
        draw = ImageDraw.Draw(fade)
        for y in range(IH):
            draw.line((0, y, IW, y), fill=(0, 0, 0, round(240 * max(0, (y - IH * .48) / (IH * .52)) ** 1.1)))
        bg.alpha_composite(fade)
        card.alpha_composite(bg, (M, M))

        # Final production settings derived from the local preview script.
        score = number(f'{home_goals}-{away_goals}', PHASE_SCORE_FONT_SIZE, key, assets)
        y = (1210 if shootout else 1220) - PHASE_GROUP_LIFT

        # Keep the score fixed at card center, independent of crest widths.
        # Measure gaps from visible alpha bounds, preserving PNG padding.
        logo_height = max(1, round(score.height * PHASE_LOGO_HEIGHT_FACTOR))
        home_mark = phase_logo(home_name, home_id, key, assets, logo_height)
        away_mark = phase_logo(away_name, away_id, key, assets, logo_height)
        score_x, home_x, away_x = phase_group_positions(
            home_mark, away_mark, score.width, W, gap=28
        )

        soft_place(card, score, (score_x, y - score.height // 2), blur=9, opacity=.60, key=key)
        if home_mark is not None:
            soft_place(card, home_mark, (home_x, y - home_mark.height // 2), blur=9, opacity=.60, key=key)
        if away_mark is not None:
            soft_place(card, away_mark, (away_x, y - away_mark.height // 2), blur=9, opacity=.60, key=key)

        if shootout:
            hp, ap = shootout
            if hp == ap:
                raise ValueError('Rigori non conclusi')
            # home_name/away_name sono nomi ESPN (servono ai loghi): il testo resta in italiano.
            winner = team_names.translate_team(home_name if hp > ap else away_name)
            text = f'{winner} VINCE {max(hp, ap)}-{min(hp, ap)} AI RIGORI'.upper()
            caption = number(text, 36, key, assets)
            if caption.width > IW - 40:
                caption = ImageOps.contain(caption, (IW - 40, caption.height))
            soft_place(
                card,
                caption,
                ((W - caption.width) // 2, PHASE_PENALTY_CAPTION_Y),
                blur=5,
                opacity=.50,
                key=key,
            )

    return png(brand(card, key, assets))


def tinted_shadow(canvas, mask, key, blur, opacity, offset):
    shifted = Image.new('L', canvas.size)
    shifted.paste(mask, (0, offset))
    shadow = Image.new('RGBA', canvas.size, ImageColor.getrgb(SHADOW.get(key, '#000000')) + (255,))
    shadow.putalpha(shifted.filter(ImageFilter.GaussianBlur(blur)).point(lambda a: round(a * opacity)))
    canvas.alpha_composite(shadow)


def place_word(card, word, saved, key='home'):
    x = (1086 - word.width) // 2
    y = 1115 + BOTTOM_SHIFT - word.height
    mask = Image.new('L', card.size)
    mask.paste(word.getchannel('A'), (x, y))
    tinted_shadow(card, mask, key, blur=14, opacity=.55, offset=6)
    card.alpha_composite(word, (x, y))


def soft_place(canvas, layer, position, blur=8, opacity=.55, offset=5, key='home'):
    mask = Image.new('L', canvas.size)
    mask.paste(layer.getchannel('A'), position)
    tinted_shadow(canvas, mask, key, blur=max(4, blur * .8), opacity=opacity * .8, offset=min(offset, 4))
    canvas.alpha_composite(layer, position)


def ucl_gradient(source, assets, rng, lit=True, stops=None):
    """UCL lettering: 3-stop gradient with a random angle, a shifting middle stop and soft waves,
    lit by the same contour texture as the other themes."""
    source = source.convert('RGBA')
    alpha = source.getchannel('A')
    box = alpha.point(lambda a: 255 if a > 100 else 0).getbbox()
    if not box:
        return textured(source, 'ucl', assets)
    bw, bh = box[2] - box[0], box[3] - box[1]
    gw = 64
    gh = max(8, round(gw * bh / bw))
    angle = rng.uniform(0, 2 * math.pi)
    waves = [(rng.uniform(1.5, 3.5), rng.uniform(0, 2 * math.pi), rng.uniform(.04, .09), rng.uniform(0, 2 * math.pi))
             for _ in range(2)]
    values = []
    for j in range(gh):
        v = (j / (gh - 1) - .5) * bh / bw
        for i in range(gw):
            u = i / (gw - 1) - .5
            value = u * math.cos(angle) + v * math.sin(angle)
            for f, ph, amp, b in waves:
                value += amp * math.sin(f * math.pi * (u * math.cos(b) + v * math.sin(b)) * 2 + ph)
            values.append(value)
    lo, hi = min(values), max(values)
    flip = rng.random() < .5
    grid = Image.new('L', (gw, gh))
    grid.putdata([round(255 * (1 - (x - lo) / (hi - lo) if flip else (x - lo) / (hi - lo))) for x in values])
    ramp = Image.new('L', source.size, 0)
    ramp.paste(grid.resize((bw, bh), Image.Resampling.BICUBIC), box[:2])
    magenta, violet, ice = stops or UCL_GRADIENT
    base = ImageOps.colorize(ramp, black=magenta, white=ice, mid=violet, midpoint=round(255 * rng.uniform(.32, .58)))
    if not lit:                       # plain gradient, no texture light (JR mark)
        out = base.convert('RGBA')
        out.putalpha(alpha)
        return out
    # Same light modulation as the other themes' texture tint.
    texture = Image.open(Path(assets) / 'word_textures' / f'{texture_key("ucl")}.png').convert('RGB')
    gray = ImageOps.autocontrast(
        ImageOps.grayscale(ImageOps.fit(texture, source.size, method=Image.Resampling.LANCZOS)), cutoff=1)
    hist = gray.histogram()
    mean = sum(i * c for i, c in enumerate(hist)) / sum(hist)
    light = gray.point(lambda x: round(128 * (1 + .55 * (x - mean) / 255))).convert('F')
    bands = [ImageMath.lambda_eval(lambda a: a['c'] * a['m'] / 128, c=band.convert('F'), m=light).convert('L')
             for band in base.split()]
    out = Image.merge('RGB', bands).convert('RGBA')
    out.putalpha(alpha)
    return out


def center_name(card, label, font, *, key=None, assets=None):
    box = font.getbbox(label)
    layer = Image.new('RGBA', (box[2] - box[0] + 8, box[3] - box[1] + 8))
    ImageDraw.Draw(layer).text((4 - box[0], 4 - box[1]), label, font=font, fill='white')
    layer = layer.crop(layer.getchannel('A').getbbox())
    if key and assets is not None:
        # Stessa texture del kit dei loghi e della scritta GOAL/SAVED, non bianco piatto.
        # UCL: sfumatura casuale con texture, come le scritte.
        layer = (ucl_gradient(layer, assets, random.Random(), stops=UCL_TEXT_GRADIENT) if key == 'ucl'
                 else textured(layer, key, assets, True))
    card.alpha_composite(layer, ((card.width - layer.width) // 2, 1254 + BOTTOM_SHIFT))
