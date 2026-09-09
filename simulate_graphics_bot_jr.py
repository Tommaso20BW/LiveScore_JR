"""Manual integration test: ESPN-shaped events, real renderer/Canva/Telegram.

Does not run the polling loop, Gist, scheduler, or production channel. Each
scenario asserts its expected card/no-card result before sending to Bot JR.
"""
import io
import json
import os
import time
from pathlib import Path
from PIL import Image
import juve_bot_espn as bot

OUT = Path('simulation_output')
REPORT = []
COMMON = dict(home_id='111',away_id='110',home_name='Juventus',away_name='Inter',
              league_slug='uefa.champions',league_name='UEFA Champions League')
DATA = {'header':{'competitions':[{'competitors':[
    {'id':'111','homeAway':'home','team':{'id':'111','displayName':'Juventus'}},
    {'id':'110','homeAway':'away','team':{'id':'110','displayName':'Inter'}}]}]},
    'boxscore':{'teams':[{'homeAway':'home','team':{'id':'111','uniform':{'type':'home'}}}]}}

def record(label, **values):
    REPORT.append(dict(scenario=label,**values))
    (OUT/'report.json').write_text(json.dumps(REPORT,indent=2),encoding='utf-8')
    print(f'TEST PASS: {label}',flush=True)

def send(label, photo=None):
    text=f'<b>TEST SIMULATO · {label}</b>\n\nJuventus — Inter'
    if photo:
        assert Image.open(io.BytesIO(photo)).size == (1086,1448)
        (OUT/f'{len(REPORT):02d}.png').write_bytes(photo)
        mid, sent = bot.send_telegram_goal_get_id(text,photo)
        assert mid and sent, f'Foto non consegnata: {label}'
    else:
        mid=bot.send_telegram_get_id(text)
        assert mid, f'Testo non consegnato: {label}'
    record(label,message_id=mid,photo=bool(photo))
    time.sleep(1.2)
    return mid

def parsed(kind,minute,name,team,period=1):
    payload=dict(DATA,keyEvents=[{'id':'test-'+str(minute),'type':{'text':kind},
        'clock':{'displayValue':str(minute)},'period':{'number':period},
        'team':{'id':team},'participants':[{'athlete':{'displayName':name}}]}])
    events=bot.parse_events(payload,'Juventus','Inter','111','110')
    assert len(events)==1, f'ESPN parsing: {kind}'
    return events[0]

def goal(kind,minute,name,team,score,expected,period=1):
    ev=parsed(kind,minute,name,team,period)
    card=bot.prepara_grafica_goal(data_espn=DATA,scorer_name=ev['player_name'],
        goal_type=ev['type'],scoring_team_id=bot.goal_scoring_team_id(ev,'111','110'),
        minute=ev['minute_disp'],home_goals=score[0],away_goals=score[1],
        event_key='simulation',**COMMON)
    assert bool(card)==expected, f'Card inattesa: {kind} {team}'
    mid=send(f"{minute}' · {name or 'Marcatore in attesa'} · {kind} · {score[0]}-{score[1]}",card.png if card else None)
    return mid,card

def phase(kind,score=(0,0),shootout=None):
    photo=bot.build_phase_graphic(kind=kind,data_espn=DATA,home_goals=score[0],away_goals=score[1],shootout=shootout,**COMMON)
    assert photo, f'{kind}: composizione o Canva falliti'
    return send(kind.upper()+f' · {score[0]}-{score[1]}',photo)

def run():
    if os.environ.get('SIMULATION_BOT_JR')!='true' or not bot.BOT_JR_CHAT_ID or bot.CHAT_ID != bot.BOT_JR_CHAT_ID:
        raise RuntimeError('Test consentito soltanto su Bot JR')
    if bot.GIST_ID or bot.TELEGRAM_AUTO_DELETE_SECONDS:
        raise RuntimeError('Il test non deve modificare lo stato live o cancellare messaggi')
    OUT.mkdir(exist_ok=True)
    # Guard every Telegram API call, including future edits added to this script.
    original=bot._tg_post
    def guarded(method,payload=None,data=None,files=None,timeout=10):
        target=(payload or data or {}).get('chat_id')
        if str(target)!=str(bot.BOT_JR_CHAT_ID) or method=='deleteMessage':
            raise RuntimeError('Destinazione o operazione non consentita nel test')
        return original(method,payload=payload,data=data,files=files,timeout=timeout)
    bot._tg_post=guarded
    send('INIZIO TEST · eventi ESPN simulati, Canva e invii reali')
    phase('kick')
    mid,_=goal('goal',12,'','111',(1,0),False)
    card=bot.prepara_grafica_goal(data_espn=DATA,scorer_name='Kenan Yildiz',goal_type='goal',scoring_team_id='111',minute=12,home_goals=1,away_goals=0,event_key='simulation',**COMMON)
    assert card and card.player_path
    ok,same,photo=bot.replace_corrected_goal_message(mid,False,'<b>TEST · 12′ GOAL YILDIZ · 1-0</b>',card)
    assert ok and same==mid and photo
    record('Testo convertito in foto, stesso message_id',message_id=same)
    corrected=bot.prepara_grafica_goal(data_espn=DATA,scorer_name='Nick Woltemade',goal_type='goal',scoring_team_id='111',minute=12,home_goals=1,away_goals=0,event_key='simulation',**COMMON)
    assert corrected and corrected.player_path
    ok,same,photo=bot.replace_corrected_goal_message(mid,True,'<b>TEST · Marcatore corretto: WOLTEMADE · 1-0</b>',corrected)
    assert ok and same==mid and photo
    record('Correzione marcatore e foto, stesso message_id',message_id=same)
    goal('goal',24,'Lautaro Martinez','110',(1,1),False)
    _,own=goal('own goal',31,'Alessandro Bastoni','110',(2,1),True)
    assert own.player is None
    goal('penalty goal','45+12','Kenan Yildiz','111',(3,1),True)
    phase('half',(3,1))
    send('INIZIO SECONDO TEMPO · solo testo')
    goal('own goal',52,'Federico Gatti','111',(3,2),False,2)
    for minute,kind in [(58,'penalty missed'),(60,'penalty saved')]:
        ev=parsed(kind,minute,'Lautaro Martinez','110',2)
        card=bot.prepara_grafica_parata_rigore(data_espn=DATA,penalty_event=ev,goalkeeper_name='Guglielmo Vicario',minute=minute,home_goals=3,away_goals=2,event_key='simulation',**COMMON)
        assert bool(card)==(kind=='penalty saved')
        send(f"{minute}' · {kind}",card.png if card else None)
    goal('goal',61,'Lautaro Martinez','110',(3,3),False,2)
    _,missing=goal('goal',67,'Marcatore Senza Foto','111',(4,3),True,2)
    assert missing.player is None
    goal('goal','90+12','Marcus Thuram','110',(4,4),False,2)
    for label in ('FINE TEMPI REGOLAMENTARI · 4-4','INIZIO SUPPLEMENTARI'):
        send(label+' · solo testo')
    goal('goal',105,'Kenan Yildiz','111',(5,4),True,3)
    send('INTERVALLO SUPPLEMENTARI · solo testo')
    goal('goal','120+12','Lautaro Martinez','110',(5,5),False,4)
    send('CALCI DI RIGORE · solo testo')
    for i in range(5):
        goal('penalty goal',121+i*2,'Kenan Yildiz','111',(5,5),False,5)
        goal('penalty goal' if i<4 else 'penalty missed',122+i*2,'Lautaro Martinez','110',(5,5),False,5)
    phase('full',(5,5),(5,4))
    # Additional recovery-minute and palette checks use the same public renderer.
    for league,kit in [('ita.1','home'),('ita.1','away'),('ita.1','third'),('uefa.europa','home'),('uefa.europa.conf','home')]:
        import goal_graphics as graphics
        # ESPN's conference slug is uefa.europa.conf; pass its full competition name.
        comp='UEFA Conference League' if league.endswith('.conf') else league
        card=graphics.render_goal_card(scorer_name='Kenan Yildiz',minute='90+12',home_name='Juventus',away_name='Inter',home_id='111',away_id='110',home_goals=1,away_goals=0,kit=kit,competition=comp)
        send(f'PALETTE {comp} · {kit}',card.png)
    import goal_graphics as graphics
    card=graphics.render_saved_card(goalkeeper_name='Guglielmo Vicario',minute='120+12',home_name='Juventus',away_name='Inter',home_id='111',away_id='110',home_goals=0,away_goals=0,competition='uefa.champions')
    send('SAVED · 120+12 · controllo minuto',card.png)
    friendly=dict(COMMON,league_slug='club.friendly')
    assert bot.build_phase_graphic(kind='full',data_espn=DATA,**friendly) is None
    record('Amichevole: nessuna grafica')
    send('TEST COMPLETATO · rapporto e PNG negli artifact GitHub')

if __name__=='__main__': run()
