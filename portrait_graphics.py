"""Approved 3:4 compositor. No generation, Canva edits, or Telegram side effects."""
import io
from pathlib import Path
from PIL import Image, ImageDraw, ImageOps, ImageFont, ImageColor, ImageStat, ImageFilter, ImageEnhance
import goal_graphics as g

W, H, M = 1086, 1448, 76
IW, IH = W - 2*M, H - 2*M
COLORS = dict(home='#FACA02', away='#ED95AE', third='#C7A852',
              saved_italia='#D97C30', ucl='#8DD6FF', uel='#FFAC38', conference='#A1EF46')

def theme(kit='home', competition='', saved=False):
    value = competition.lower()
    if 'conference' in value or 'europa.conf' in value: return 'conference'
    if 'champions' in value: return 'ucl'
    if 'europa' in value: return 'uel'
    return kit if kit in ('home', 'away', 'third') else 'home'

def texture_key(key):
    return 'saved' if key == 'saved_italia' else key if key in ('home','away','third') else 'home'

def tight(source, white_mask=False):
    source = source.convert('RGBA')
    alpha = source.getchannel('A')
    if white_mask and alpha.getextrema() == (255,255): alpha = ImageOps.grayscale(source)
    source.putalpha(alpha)
    box = alpha.point(lambda a: 255 if a > 100 else 0).getbbox()
    if not box: raise ValueError('Asset vuoto')
    return source.crop(box)

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
    channels = [texture.point(lambda v,c=c: round(max(0,min(255,c*(.75+.4*v/255)+(18*v/255 if c<12 else 0))))) for c in ImageColor.getrgb(color)]
    result = Image.merge('RGB',channels).convert('RGBA')
    result.putalpha(source.getchannel('A'))
    return result

def brand(card, key, assets):
    mark = tight(Image.open(assets/'portrait/jr.png'))
    height = round(H*58/1280)
    mark = mark.resize((round(mark.width*height/mark.height),height),Image.Resampling.LANCZOS)
    color = {'ucl':'#8DD6FF','uel':'#000000','conference':'#000000','away':'#F6B5CA'}.get(key,COLORS[key])
    mark = textured(mark,key,assets,True,color,bright=key=='home')
    x = W-round(W*16/960)-mark.width
    assert x > W-M
    if key == 'home':
        shadow_mask = Image.new('L',card.size)
        shadow_mask.paste(mark.getchannel('A'),(x+1,round(H*13/1280)+4))
        shadow = Image.new('RGBA',card.size,'black')
        shadow.putalpha(shadow_mask.filter(ImageFilter.GaussianBlur(9)).point(lambda a:round(a*.35)))
        card.alpha_composite(shadow)
    card.alpha_composite(mark,(x,round(H*13/1280)))
    return card

def logo(name, tid, key, assets, height):
    source, origin = g.resolve_team_logo_source(name,str(tid),assets)
    if source is None: return None
    source = tight(source)
    source = source.resize((round(source.width*height/source.height),height),Image.Resampling.LANCZOS)
    return textured(source,key,assets,True) if origin == 'FCLogo' else source

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

def event(*, player, scorer_name, minute, home_name, away_name, home_id, away_id,
          kit, saved=False, suffix='', competition='', pose=None, event_key='', assets=g.DEFAULT_ASSET_DIR):
    assets = Path(assets)
    key = theme(kit,competition,saved)
    background = assets/'portrait'/f'{key}_{"saved" if saved else "goal"}_1086x1448.png'
    domestic_saved = saved and key in ('home', 'away', 'third')
    if domestic_saved:
        background = assets/'portrait'/f'{key}_clean_1086x1448.png'
    card = Image.open(background).convert('RGBA')
    if key == 'ucl': card = vivid_background(card)
    panel = card.crop((M,M,W-M,H-M))
    if domestic_saved:
        heading = tight(Image.open(assets/'overlays/front_saved.png'), True)
        heading = heading.resize((IW+100, round(heading.height*(IW+100)/heading.width)), Image.Resampling.LANCZOS)
        panel.alpha_composite(textured(heading,key,assets),(-50,-60))
    path = None
    pose = pose or 'arms_crossed'
    if player:
        path = g.resolve_player_path(player,'third' if saved else kit,pose,assets)
        if path and Path(path).is_file():
            with Image.open(path) as raw:
                if not g._has_real_transparency(raw):
                    raise g.GoalGraphicUnavailable('PNG giocatore non scontornato')
                portrait = tight(raw)
            portrait = portrait.resize((round(portrait.width*1450/portrait.height),1450),Image.Resampling.LANCZOS)
            panel.alpha_composite(portrait,((IW-portrait.width)//2,-25))
            card.alpha_composite(portrait.crop((0,0,portrait.width,25)),((W-portrait.width)//2,M-25))
        else: path = None
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
    font = ImageFont.truetype(str(assets/'fonts/DharmaGothicEBold.otf'),32 if saved else 36)
    minute_position = (M+14, M+160) if domestic_saved else (M+(45 if saved else 18), M+(128 if saved else 30))
    ImageDraw.Draw(card).text(minute_position,str(minute).rstrip("'’")+"'",font=font,fill=COLORS[key],anchor='lt')
    marks = [logo(name,tid,key,assets,64) for name,tid in [(home_name,home_id),(away_name,away_id)]]
    marks = [mark for mark in marks if mark is not None]
    total = sum(mark.width for mark in marks)+max(0,len(marks)-1)*20
    x = (W-total)//2
    for mark in marks:
        soft_place(card,mark,(x,1180-mark.height//2),blur=6,opacity=.50)
        x += mark.width+20

    label = (scorer_name+suffix).upper()
    size = 29
    while size > 14 and g._font(size).getlength(label) > IW-40: size -= 1
    center_name(card,label,g._font(size))
    return g.RenderedGoal(png(brand(card,key,assets)),player if path else None,scorer_name,
                          'saved' if saved else kit,pose,path,background)

def phase(*, kind, home_name, away_name, home_id, away_id, home_goals=0, away_goals=0,
          kit='home', competition='', layers=None, shootout=None, assets=g.DEFAULT_ASSET_DIR):
    if kind not in ('kick','half','full'): raise ValueError('Fase senza grafica')
    assets = Path(assets)
    key = theme(kit,competition)
    card = Image.open(assets/'portrait'/f'{key}_clean_1086x1448.png').convert('RGBA')
    if key == 'ucl': card = vivid_background(card)
    word = tight(Image.open(assets/'portrait'/f'{kind}.png'),True)
    if kind == 'kick':
        word = ImageOps.contain(word,(600,600),Image.Resampling.LANCZOS)
        top = (H-64-38-word.height)//2
        card.alpha_composite(textured(word,key,assets),((W-word.width)//2,top+102))
        for name,tid,cx in [(home_name,home_id,500),(away_name,away_id,581)]:
            mark = logo(name,tid,key,assets,64)
            if mark: soft_place(card,mark,(cx-mark.width//2,top),blur=6,opacity=.50)
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
        score = number(f'{home_goals}-{away_goals}',200,key,assets)
        y = 1210 if shootout else 1220
        soft_place(card,score,((W-score.width)//2,y-score.height//2),blur=9,opacity=.60)
        for name,tid,left in [(home_name,home_id,True),(away_name,away_id,False)]:
            mark = logo(name,tid,key,assets,score.height)
            if mark:
                x = (W-score.width)//2-40-mark.width if left else (W+score.width)//2+40
                soft_place(card,mark,(x,y-mark.height//2),blur=9,opacity=.60)
        if shootout:
            hp,ap = shootout
            if hp == ap: raise ValueError('Rigori non conclusi')
            winner = home_name if hp > ap else away_name
            text = f'{winner} VINCE {max(hp,ap)}-{min(hp,ap)} AI RIGORI'.upper()
            caption = number(text,36,key,assets)
            if caption.width > IW-40: caption = ImageOps.contain(caption,(IW-40,caption.height))
            soft_place(card,caption,((W-caption.width)//2,1320),blur=5,opacity=.50)
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
