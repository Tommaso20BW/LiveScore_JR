"""Approved 3:4 compositor. No generation, Canva edits, or Telegram side effects."""
import io
from pathlib import Path
from PIL import Image, ImageDraw, ImageOps, ImageFont, ImageColor, ImageStat, ImageFilter, ImageEnhance
import goal_graphics as g

W, H, M = 1086, 1448, 76
IW, IH = W - 2*M, H - 2*M
COLORS = dict(home='#FACA02', away='#ED95AE', third='#C7A852',
              ucl='#8DD6FF', uel='#FFAC38', conference='#A1EF46')

# Layout phase cards (HALF / FULL / END OF 90) on canvas 1086x1448.
PHASE_SCORE_FONT_SIZE = 300
PHASE_LOGO_HEIGHT_RATIO = 0.43
PHASE_LOGO_GAP = 28
PHASE_GROUP_RAISE = 65
PHASE_SHOOTOUT_CAPTION_MIN_GAP = 36
PHASE_SHOOTOUT_BOTTOM_MARGIN = 28

def theme(kit='home', competition='', saved=False):
    value = competition.lower()
    if 'conference' in value or 'europa.conf' in value or 'europa_conf' in value: return 'conference'
    if 'champions' in value: return 'ucl'
    if 'europa' in value: return 'uel'
    return kit if kit in ('home', 'away', 'third') else 'home'

def texture_key(key):
    return key if key in ('home','away','third') else 'home'

def tight(source, white_mask=False):
    source = source.convert('RGBA')
    alpha = source.getchannel('A')
    if white_mask and alpha.getextrema() == (255,255): alpha = ImageOps.grayscale(source)
    source.putalpha(alpha)
    box = alpha.point(lambda a: 255 if a > 100 else 0).getbbox()
    if not box: raise ValueError('Asset vuoto')
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
    # Sara questa coordinata ad essere allineata al centro della card.
    anchor_x = (source.width / 2 - box[0]) * scale
    return portrait, anchor_x

def textured(source, key, assets, zoom=False, color=None, bright=False):
    color = color or COLORS[key]
    texture = Image.open(assets/'word_textures'/f'{texture_key(key)}.png')
    if not zoom:
        return g._tint_textured_overlay(source, color, texture, preserve_source_detail=False)
    texture = ImageOps.autocontrast(texture.convert('L'), cutoff=1)
    w,h = texture.size
    if bright:
        patches = [texture.crop((x*w//8,y*h//8,x*w//8+w//4,y*h//8+h//4)) for x in range(7) for y in range(7)]
        texture = max(patches, key=lambda im: ImageStat.Stat(im).mean[0])
    else: texture = texture.crop((w*3//8,h*3//8,w*5//8,h*5//8))
    texture = ImageOps.fit(texture, source.size, method=Image.Resampling.LANCZOS)
    if key == 'third':
        # Restore detail lost by the enlarged crop without adding more folds.
        texture = ImageEnhance.Contrast(texture).enhance(2.0)
    channels = [texture.point(lambda v,c=c: round(max(0,min(255,c*(.75+.4*v/255)+(18*v/255 if c<12 else 0))))) for c in ImageColor.getrgb(color)]
    result = Image.merge('RGB',channels).convert('RGBA')
    result.putalpha(source.getchannel('A'))
    return result

def brand(card, key, assets):
    mark = tight(Image.open(assets/'portrait/jr.png'))
    height = round(H*58/1280)
    mark = mark.resize((round(mark.width*height/mark.height),height),Image.Resampling.LANCZOS)
    color = {'home':'#102B46','ucl':'#8DD6FF','uel':'#232323','conference':'#232323','away':'#F6B5CA'}.get(key,COLORS[key])
    mark = textured(mark,key,assets,True,color)
    x = W-round(W*16/960)-mark.width
    assert x > W-M
    card.alpha_composite(mark,(x,round(H*13/1280)))
    return card

def logo(name, tid, key, assets, height):
    source, origin = g.resolve_team_logo_source(name,str(tid),assets)
    if source is None: return None
    source = tight(source)
    source = source.resize((round(source.width*height/source.height),height),Image.Resampling.LANCZOS)
    return textured(source,key,assets,True) if origin == 'FCLogo' else source

def centered_logo_positions(marks, center, gap=20):
    """Center the tight visible bounds as a group, not fixed logo slots."""
    marks = [mark for mark in marks if mark is not None]
    total = sum(mark.width for mark in marks) + max(0, len(marks)-1)*gap
    x = round(center-total/2)
    for mark in marks:
        yield mark, x
        x += mark.width+gap


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
    return textured(source, key, assets, True) if origin == 'FCLogo' else source


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
    font = ImageFont.truetype(str(assets/'fonts/DharmaGothicEBold.otf'),size)
    box = font.getbbox(text)
    layer = Image.new('RGBA',(max(1,box[2]-box[0]),max(1,box[3]-box[1])))
    ImageDraw.Draw(layer).text((-box[0],-box[1]),text,font=font,fill='white')
    return textured(layer,key,assets,True)

def png(card):
    stream = io.BytesIO()
    card.convert('RGB').save(stream,format='PNG')
    return stream.getvalue()


def saved_heading(assets):
    heading = tight(Image.open(Path(assets)/'overlays/front_saved.png'), True)
    # Uniform scaling preserves the supplied lettering's original proportions.
    width = 1034
    heading = heading.resize((width, round(heading.height*width/heading.width)), Image.Resampling.LANCZOS)
    layer = Image.new('RGBA', (IW, IH))
    layer.alpha_composite(heading, (-50, -22))
    return layer


def saved_minute_position(heading, text, font):
    """Keep the entire minute box plus 4px clearance in the S's upper hollow."""
    box = font.getbbox(text)
    width, height = box[2]-box[0], box[3]-box[1]
    mask = heading.getchannel('A').point(lambda a: 255 if a > 100 else 0)
    candidates = sorted(((x, y) for y in range(8, 51) for x in range(8, 81)),
                        key=lambda xy: (xy[0]-20)**2+(xy[1]-14)**2)
    for x, y in candidates:
        if mask.crop((x-4, y-4, x+width+4, y+height+4)).getbbox() is None:
            return M+x, M+y
    raise ValueError('Minuto SAVED senza spazio libero nella S')

def event(*, player, scorer_name, minute, home_name, away_name, home_id, away_id,
          kit, saved=False, suffix='', competition='', pose=None, event_key='', assets=g.DEFAULT_ASSET_DIR):
    assets = Path(assets)
    key = theme(kit,competition,saved)
    background = assets/'portrait'/f'{key}_{"clean" if saved else "goal"}_1086x1448.png'
    card = Image.open(background).convert('RGBA')
    if key == 'ucl': card = vivid_background(card)
    panel = card.crop((M,M,W-M,H-M))
    if saved:
        heading = saved_heading(assets)
        panel.alpha_composite(textured(heading,key,assets))
    path = None
    pose = pose or 'arms_crossed'
    if player:
        path = g.resolve_player_path(player,kit,pose,assets)
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
            panel.alpha_composite(portrait,(panel_x,-25))

            # I primi 25 px salgono sopra il pannello interno: manteniamo la
            # stessa identica ancora X anche nella porzione compositata sul card.
            card.alpha_composite(
                portrait.crop((0,0,portrait.width,25)),
                (M + panel_x, M-25)
            )
        else:
            path = None
    fade = Image.new('RGBA',panel.size)
    draw = ImageDraw.Draw(fade)
    for y in range(520,IH):
        draw.line((0,y,IW,y),fill=(0,0,0,round(238*min(1,(y-520)/(IH-520))**1.35)))
    panel.alpha_composite(fade)
    card.alpha_composite(panel,(M,M))
    word = tight(Image.open(assets/'overlays'/('front_saved.png' if saved else 'front_goal.png')),True)
    word = ImageOps.contain(word,(IW+44,340),Image.Resampling.LANCZOS)
    word = textured(word,key,assets)
    place_word(card,word,saved)
    font = ImageFont.truetype(str(assets/'fonts/DharmaGothicEBold.otf'),24 if saved else 36)
    minute_text = str(minute).rstrip("'’")+"'"
    minute_position = saved_minute_position(heading, minute_text, font) if saved else (M+18, M+30)
    ImageDraw.Draw(card).text(minute_position,minute_text,font=font,fill=COLORS[key],anchor='lt')
    marks = [logo(name,tid,key,assets,64) for name,tid in [(home_name,home_id),(away_name,away_id)]]
    for mark, x in centered_logo_positions(marks, W/2):
        soft_place(card,mark,(x,1180-mark.height//2),blur=6,opacity=.50)

    label = (scorer_name+suffix).upper()
    size = 29
    while size > 14 and g._font(size).getlength(label) > IW-40: size -= 1
    center_name(card,label,g._font(size))
    return g.RenderedGoal(png(brand(card,key,assets)),player if path else None,scorer_name,
                          'saved' if saved else kit,pose,path,background)

def phase(*, kind, home_name, away_name, home_id, away_id, home_goals=0, away_goals=0,
          kit='home', competition='', layers=None, shootout=None, assets=g.DEFAULT_ASSET_DIR):
    if kind not in ('kick','half','full','end_of_90'): raise ValueError('Fase senza grafica')
    assets = Path(assets)
    key = theme(kit,competition)
    card = Image.open(assets/'portrait'/f'{key}_clean_1086x1448.png').convert('RGBA')
    if key == 'ucl': card = vivid_background(card)
    word = tight(Image.open(assets/'portrait'/f'{kind}.png'),True)
    if kind == 'kick':
        word = ImageOps.contain(word,(600,600),Image.Resampling.LANCZOS)
        top = (H-64-38-word.height)//2
        card.alpha_composite(textured(word,key,assets),((W-word.width)//2,top+102))
        marks = [logo(name,tid,key,assets,64) for name,tid in
                 [(home_name,home_id),(away_name,away_id)]]
        for mark, x in centered_logo_positions(marks, W/2):
            soft_place(card,mark,(x,top),blur=6,opacity=.50)
    else:
        if layers is None: raise ValueError('Pagina 1 Canva non disponibile')
        # Both extracted layers share the PDF page coordinates and transform.
        bg = ImageOps.fit(Image.open(Path(layers)/'background.png').convert('RGBA'),(IW,IH),method=Image.Resampling.LANCZOS)
        player = ImageOps.fit(Image.open(Path(layers)/'player.png').convert('RGBA'),(IW,IH),method=Image.Resampling.LANCZOS)
        word = word.resize((IW-36,round(word.height*(IW-36)/word.width)),Image.Resampling.LANCZOS)
        soft_place(bg,textured(word,key,assets),(18,28),blur=12,opacity=.60)
        bg.alpha_composite(player)
        fade = Image.new('RGBA',bg.size)
        draw = ImageDraw.Draw(fade)
        for y in range(IH):
            draw.line((0,y,IW,y),fill=(0,0,0,round(240*max(0,(y-IH*.48)/(IH*.52))**1.1)))
        bg.alpha_composite(fade)
        card.alpha_composite(bg,(M,M))
        score = number(f'{home_goals}-{away_goals}',PHASE_SCORE_FONT_SIZE,key,assets)
        y = (1210 if shootout else 1220) - PHASE_GROUP_RAISE
        score_top = y-score.height//2
        score_bottom = score_top + score.height

        # Keep the score fixed at card center, independent of crest widths.
        # Measure gaps from visible alpha bounds, preserving PNG padding.
        logo_height = max(1, round(score.height * PHASE_LOGO_HEIGHT_RATIO))
        home_mark = phase_logo(home_name,home_id,key,assets,logo_height)
        away_mark = phase_logo(away_name,away_id,key,assets,logo_height)
        score_x, home_x, away_x = phase_group_positions(
            home_mark, away_mark, score.width, W, gap=PHASE_LOGO_GAP
        )

        soft_place(card,score,(score_x,score_top),blur=9,opacity=.60)
        if home_mark is not None:
            soft_place(card,home_mark,(home_x,y-home_mark.height//2),blur=9,opacity=.60)
        if away_mark is not None:
            soft_place(card,away_mark,(away_x,y-away_mark.height//2),blur=9,opacity=.60)
        if shootout:
            hp,ap = shootout
            if hp == ap: raise ValueError('Rigori non conclusi')
            winner = home_name if hp > ap else away_name
            text = f'{winner} VINCE {max(hp,ap)}-{min(hp,ap)} AI RIGORI'.upper()
            caption = number(text,36,key,assets)
            if caption.width > IW-40: caption = ImageOps.contain(caption,(IW-40,caption.height))
            caption_y = max(
                1320 - PHASE_GROUP_RAISE,
                score_bottom + PHASE_SHOOTOUT_CAPTION_MIN_GAP,
            )
            caption_y = min(
                caption_y,
                H - M - caption.height - PHASE_SHOOTOUT_BOTTOM_MARGIN,
            )
            soft_place(card,caption,((W-caption.width)//2,caption_y),blur=5,opacity=.50)
    return png(brand(card,key,assets))


def vivid_background(card):
    # Regrade only the fabric asset, never the player's photograph.
    frame = ImageOps.colorize(ImageOps.grayscale(card), '#031426', '#4EAEE0',
                             mid='#0B4776', midpoint=150).convert('RGBA')
    panel = card.crop((76,76,1010,1372))
    # The baked source includes two bright antialiased frame pixels inside the
    # right edge (x=1008/1009). Extend adjacent fabric across that seam only.
    panel.paste(panel.crop((panel.width-6,0,panel.width-5,panel.height)).resize((3,panel.height)),(panel.width-3,0))
    panel = ImageEnhance.Color(panel).enhance(1.22)
    panel = ImageEnhance.Contrast(panel).enhance(1.08)
    panel = ImageEnhance.Brightness(panel).enhance(1.12)
    frame.paste(panel,(76,76))
    return frame

def place_word(card,word,saved):
    x=(1086-word.width)//2
    y=1115-word.height
    mask=Image.new('L',card.size)
    mask.paste(word.getchannel('A'),(x,y+10))
    shadow=Image.new('RGBA',card.size,'black')
    shadow.putalpha(mask.filter(ImageFilter.GaussianBlur(18)).point(lambda a:round(a*.70)))
    card.alpha_composite(shadow)
    card.alpha_composite(word,(x,y))

def soft_place(canvas,layer,position,blur=8,opacity=.55,offset=5):
    mask=Image.new('L',canvas.size)
    mask.paste(layer.getchannel('A'),(position[0],position[1]+offset))
    shadow=Image.new('RGBA',canvas.size,'black')
    shadow.putalpha(mask.filter(ImageFilter.GaussianBlur(blur)).point(lambda a:round(a*opacity)))
    canvas.alpha_composite(shadow)
    canvas.alpha_composite(layer,position)

def center_name(card,label,font):
    box=font.getbbox(label)
    layer=Image.new('RGBA',(box[2]-box[0]+8,box[3]-box[1]+8))
    ImageDraw.Draw(layer).text((4-box[0],4-box[1]),label,font=font,fill='white')
    layer=layer.crop(layer.getchannel('A').getbbox())
    card.alpha_composite(layer,((card.width-layer.width)//2,1254))
