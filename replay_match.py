"""Explicit historical replay to Bot JR only; never reads/writes live match state."""
import argparse
import json
import os
from pathlib import Path
import time
import juve_bot_espn as bot
import portrait_graphics as portrait
from canva_page_one import export_page_one


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--event', required=True)
    parser.add_argument('--league', default='ita.1')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    if not args.event.isdecimal():
        raise ValueError('Invalid ESPN event')
    data = bot.fetch_evento(args.event, args.league)
    comp = data['header']['competitions'][0]
    hid, aid, hn, an, final_h, final_a = bot.parse_score(comp['competitors'])
    if not bot.stats_eligible(hid, aid, args.league) or not comp['status']['type'].get('completed'):
        raise ValueError('Replay requires a completed competitive Juventus game')
    events = bot.parse_events(data, hn, an, hid, aid)
    events.sort(key=lambda e: (e.get('period') or (1 if e['minute'] <= 45 else 2), e['minute'], e['seq']))
    goals = [e for e in events if e['type'] in ('goal', 'own goal', 'penalty goal')]
    if sum(e['team_id'] == hid for e in goals) != final_h or sum(e['team_id'] == aid for e in goals) != final_a:
        raise ValueError('Parsed scoring events do not match ESPN final score; refusing replay')
    if any((e.get('period') or 0) > 2 for e in events):
        raise ValueError('This replay supports regulation-only matches')
    print(json.dumps({'event':args.event,'match':f'{hn} {final_h}-{final_a} {an}',
        'events':[(e['minute_disp'],e['type'],e['player_name']) for e in events]},ensure_ascii=False),flush=True)
    if args.dry_run:
        return
    if not bot.BOT_JR_CHAT_ID or bot.CHAT_ID != bot.BOT_JR_CHAT_ID or not bot.BOT_TOKEN:
        raise RuntimeError('Replay is restricted to configured Bot JR destination')
    if bot.GIST_ID or bot.TELEGRAM_AUTO_DELETE_SECONDS:
        raise RuntimeError('Replay must not mutate live Gist or auto-delete queue')
    bot.GOAL_GRAPHICS_ENABLED = True
    kit = bot.rileva_kit_juve(data,hid,aid,hn,an,args.league,'Serie A')
    layers = export_page_one(bot.SESSION,bot.get_valid_token(),bot.CANVA_DESIGN_ID,Path('replay_canva_cache'))
    output=Path('replay_output');output.mkdir(exist_ok=True)
    plan=[]
    tag=f'🧪 TEST REPLAY • ESPN {args.event}'
    def add(text, image=None):
        plan.append((f'{tag}\n\n{text}',image))
    def phase(kind,title,h,a):
        image=portrait.phase(kind=kind,home_name=hn,away_name=an,home_id=hid,away_id=aid,
            home_goals=h,away_goals=a,kit=kit,competition=args.league,layers=layers)
        add(f'<b>{title}</b>\n\n{bot.esc(hn)} {h}-{a} {bot.esc(an)}',image)
    add('Simulazione accelerata della partita del '+comp['date'][:10]+'.\n'
        'Eventi reali ESPN. Statistiche solo finali: nessun dato del primo tempo inventato.\n'
        'Immagine HALF/FULL TIME dalla pagina 1 Canva attuale.')
    phase('kick','KICK OFF',0,0)
    h=a=0
    halftime=False
    for e in events:
        if (e.get('period',0)>=2 or e['minute']>49) and not halftime:
            phase('half','HALF TIME',h,a)
            add('INIZIO SECONDO TEMPO')
            halftime=True
        typ=e['type']; minute=e['minute_disp']; player=bot.esc(e['player_name'])
        team=bot.esc(hn if e['team_id']==hid else an)
        if typ in ('goal','own goal','penalty goal'):
            h+=int(e['team_id']==hid); a+=int(e['team_id']==aid)
            rendered=bot.prepara_grafica_goal(data_espn=data,scorer_name=e['player_name'],goal_type=typ,
                scoring_team_id=e['team_id'],minute=minute,home_name=hn,away_name=an,home_id=hid,away_id=aid,
                home_goals=h,away_goals=a,league_slug=args.league,league_name='Serie A',event_key=f'replay|{args.event}|{e["uid"]}')
            if e['team_id']==bot.JUVE_ID and rendered is None:
                raise RuntimeError('Juventus GOAL graphic failed during preflight')
            add(f'<b>GOL {team} • {minute}′</b>\n{player}\n\n{bot.esc(hn)} {h}-{a} {bot.esc(an)}',rendered.png if rendered else None)
        elif typ=='substitution':
            add(f'<b>CAMBIO {team} • {minute}′</b>\n{player} / {bot.esc(e["assist_name"])}')
        elif typ in ('yellow card','red card','second yellow card'):
            label='AMMONIZIONE' if typ=='yellow card' else 'ESPULSIONE'
            add(f'<b>{label} • {minute}′</b>\n{player} — {team}')
    if not halftime:
        raise RuntimeError('No second-half events')
    phase('full','FULL TIME',h,a)
    stats=bot.recupera_e_genera_stats_html(data,hid,aid,hn,an,h,a,'FT','SERIE A',league_slug=args.league,event_id=args.event)
    if not stats:
        raise RuntimeError('STATS generation failed during preflight')
    add('<b>JR STATS • FULL TIME</b>\nDati finali reali ESPN.',Path(stats).read_bytes())
    receipts=[]
    for index,(caption,image) in enumerate(plan,1):
        if image:
            (output/f'{index:02d}.png').write_bytes(image)
            mid,photo=bot._send_telegram_event_photo_get_id(caption,image,filename='replay.png',label='REPLAY')
            if mid is None or not photo:
                raise RuntimeError(f'Photo delivery failed at item {index}; no automatic duplicate replay')
        else:
            mid=bot.send_telegram_get_id(caption)
            if mid is None:
                raise RuntimeError(f'Text delivery failed at item {index}')
        receipts.append({'index':index,'message_id':mid,'photo':bool(image)})
        (output/'receipts.json').write_text(json.dumps(receipts),encoding='utf-8')
        print(f'Bot JR: {index}/{len(plan)} delivered; photo={bool(image)}',flush=True)
        time.sleep(3)
    print(f'REPLAY COMPLETED: {len(receipts)} messages, {sum(r["photo"] for r in receipts)} images; live state untouched',flush=True)


if __name__=='__main__':
    main()
