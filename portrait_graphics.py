"""Approved 3:4 compositor. No generation, Canva edits, or Telegram side effects."""
import io
from pathlib import Path
from PIL import Image, ImageDraw, ImageOps, ImageFont, ImageColor, ImageStat
import goal_graphics as g

W, H, M = 1086, 1448, 76
IW, IH = W - 2*M, H - 2*M
COLORS = dict(home='#FACA02', away='#ED95AE', third='#C7A852',
              saved_italia='#D97C30', ucl='#7DB8EC', uel='#FFAC38', conference='#A1EF46')

def theme(kit='home', competition='', saved=False):
    value = competition.lower()
    if 'conference' in value or 'europa.conf' in value: return 'conference'
    if 'champions' in value: return 'ucl'
    if 'europa' in value: return 'uel'
    return 'saved_italia' if saved else kit if kit in ('home', 'away', 'third') else 'home'

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
    color = {'ucl':'#14549A','uel':'#000000','conference':'#000000','away':'#F6B5CA'}.get(key,COLORS[key])
    mark = textured(mark,key,assets,True,color,bright=key=='home')
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
    card = Image.open(background).convert('RGBA')
    panel = card.crop((M,M,W-M,H-M))
    path = None
    pose = pose or 'arms_crossed'
    if player:
        path = g.resolve_player_path(player,'third' if saved else kit,pose,assets)
        if path and Path(path).is_file():
            portrait = tight(Image.open(path))
            portrait = portrait.resize((round(portrait.width*1450/portrait.height),1450),Image.Resampling.LANCZOS)
            panel.alpha_composite(portrait,((IW-portrait.width)//2,-25))
            card.alpha_composite(portrait.crop((0,0,portrait.width,25)),((W-portrait.width)//2,M-25))
        else: path = None
    fade = Image.new('RGBA',panel.size)
    draw = ImageDraw.Draw(fade)
    for y in range(520,IH):
        draw.line((0,y,IW,y),fill=(0,0,0,round(255*min(1,(y-520)/650)**(.85 if saved else 1.15))))
    panel.alpha_composite(fade)
    card.alpha_composite(panel,(M,M))
    word = tight(Image.open(assets/'overlays'/('front_saved.png' if saved else 'front_goal.png')),True)
    word = ImageOps.contain(word,(IW-80,280),Image.Resampling.LANCZOS)
    word = textured(word,key,assets)
    card.alpha_composite(word,((W-word.width)//2,1135-word.height))
    font = ImageFont.truetype(str(assets/'fonts/DharmaGothicEBold.otf'),32 if saved else 36)
    ImageDraw.Draw(card).text((M+(45 if saved else 18),M+(128 if saved else 30)),str(minute).rstrip("'’")+"'",font=font,fill=COLORS[key],anchor='lt')
    for name,tid,cx in [(home_name,home_id,500),(away_name,away_id,581)]:
        mark = logo(name,tid,key,assets,64)
        if mark: card.alpha_composite(mark,(cx-mark.width//2,1188-mark.height//2))
    label = (scorer_name+suffix).upper()
    size = 29
    while size > 14 and g._font(size).getlength(label) > IW-40: size -= 1
    ImageDraw.Draw(card).text((W//2,1250),label,font=g._font(size),fill='white',anchor='mt')
    return g.RenderedGoal(png(brand(card,key,assets)),player if path else None,scorer_name,
                          'saved' if saved else kit,pose,path,background)

def phase(*, kind, home_name, away_name, home_id, away_id, home_goals=0, away_goals=0,
          kit='home', competition='', layers=None, shootout=None, assets=g.DEFAULT_ASSET_DIR):
    if kind not in ('kick','half','full'): raise ValueError('Fase senza grafica')
    assets = Path(assets)
    key = theme(kit,competition)
    card = Image.open(assets/'portrait'/f'{key}_clean_1086x1448.png').convert('RGBA')
    word = tight(Image.open(assets/'portrait'/f'{kind}.png'),True)
    if kind == 'kick':
        word = ImageOps.contain(word,(600,600),Image.Resampling.LANCZOS)
        top = (H-64-38-word.height)//2
        card.alpha_composite(textured(word,key,assets),((W-word.width)//2,top+102))
        for name,tid,cx in [(home_name,home_id,500),(away_name,away_id,581)]:
            mark = logo(name,tid,key,assets,64)
            if mark: card.alpha_composite(mark,(cx-mark.width//2,top))
    else:
        if layers is None: raise ValueError('Pagina 1 Canva non disponibile')
        # Both extracted layers share the PDF page coordinates and transform.
        bg = ImageOps.fit(Image.open(Path(layers)/'background.png').convert('RGBA'),(IW,IH),method=Image.Resampling.LANCZOS)
        player = ImageOps.fit(Image.open(Path(layers)/'player.png').convert('RGBA'),(IW,IH),method=Image.Resampling.LANCZOS)
        word = word.resize((IW-36,round(word.height*(IW-36)/word.width)),Image.Resampling.LANCZOS)
        bg.alpha_composite(textured(word,key,assets),(18,28))
        bg.alpha_composite(player)
        fade = Image.new('RGBA',bg.size)
        draw = ImageDraw.Draw(fade)
        for y in range(IH):
            draw.line((0,y,IW,y),fill=(0,0,0,round(240*max(0,(y-IH*.48)/(IH*.52))**1.1)))
        bg.alpha_composite(fade)
        card.alpha_composite(bg,(M,M))
        score = number(f'{home_goals}-{away_goals}',200,key,assets)
        y = 1210 if shootout else 1220
        card.alpha_composite(score,((W-score.width)//2,y-score.height//2))
        for name,tid,left in [(home_name,home_id,True),(away_name,away_id,False)]:
            mark = logo(name,tid,key,assets,score.height)
            if mark:
                x = (W-score.width)//2-40-mark.width if left else (W+score.width)//2+40
                card.alpha_composite(mark,(x,y-mark.height//2))
        if shootout:
            hp,ap = shootout
            if hp == ap: raise ValueError('Rigori non conclusi')
            winner = home_name if hp > ap else away_name
            text = f'{winner} VINCE {max(hp,ap)}-{min(hp,ap)} AI RIGORI'.upper()
            caption = number(text,36,key,assets)
            if caption.width > IW-40: caption = ImageOps.contain(caption,(IW-40,caption.height))
            card.alpha_composite(caption,((W-caption.width)//2,1320))
    return png(brand(card,key,assets))
