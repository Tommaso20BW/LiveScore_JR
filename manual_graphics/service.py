"""Manually started 30-minute service. No workflow dispatch or autorun."""
import copy
import os
import queue
import signal
import threading
import time
from .telegram import Telegram, TelegramError, DeliveryUncertain, authorized
from .coordination import Coordinator


class Service:
    def __init__(self, store, telegram, wizard, renderer, owner_id, chat_id):
        self.store, self.telegram, self.wizard, self.renderer = store, telegram, wizard, renderer
        self.owner_id, self.chat_id = owner_id, chat_id
        self.worker = None
        self.results = queue.Queue()
        self.stopped = False

    def restore(self):
        state = self.store.read('session')
        if state.get('status') == 'sending':
            state['status'] = 'uncertain'
        elif state.get('status') == 'rendering':
            state['status'] = 'ready'
        self.store.write('session', state)

    def receive(self):
        state = self.store.read('receiver')
        state.setdefault('offset', 0)
        state.setdefault('kit', [])
        state.setdefault('pending', [])
        ack = self.store.read('ack')
        state['kit'] = [u for u in state['kit'] if int(u['update_id']) >= int(ack.get('offset', 0))]
        if len(state['kit']) + len(state['pending']) >= 200:
            raise RuntimeError('Coda piena; attendo smaltimento prima di leggere altri messaggi')
        updates = self.telegram.poll(state['offset'])
        for update in updates:
            uid = int(update['update_id'])
            if uid < state['offset']:
                continue
            if authorized(update, self.owner_id, self.chat_id):
                callback = update.get('callback_query') or {}
                if str(callback.get('data') or '').startswith('kit:'):
                    state['kit'].append(update)
                elif (update.get('message', {}).get('text') or str(callback.get('data') or '').startswith('mg:')):
                    state['pending'].append(update)
            state['offset'] = uid + 1
        # One write holds routing decisions and offset together.
        self.store.write('receiver', state)

    def conversations(self):
        receiver = self.store.read('receiver')
        while receiver.get('pending'):
            update = receiver['pending'][0]
            state = self.store.read('session')
            if int(update['update_id']) > int(state.get('last_update', -1)):
                new_state, effects = self.wizard.handle(state, update, time.time())
                new_state['last_update'] = int(update['update_id'])
                self.store.write('session', new_state)
                callback_id = (update.get('callback_query') or {}).get('id')
                if callback_id:
                    try:
                        self.telegram.answer(callback_id)
                    except TelegramError:
                        pass
                for effect in effects:
                    self.telegram.prompt(effect['text'], effect.get('keyboard'))
            receiver['pending'].pop(0)
            self.store.write('receiver', receiver)

    def rendering(self):
        try:
            session_id, png, error = self.results.get_nowait()
        except queue.Empty:
            pass
        else:
            state = self.store.read('session')
            self.worker = None
            if state.get('id') == session_id and state.get('status') == 'rendering':
                if error:
                    state['status'] = 'failed'
                    self.store.write('session', state)
                    self.telegram.prompt(f'Grafica non generata ({error}). /reinvia per riprovare o /annulla.')
                else:
                    state['status'] = 'sending'
                    self.store.write('session', state)
                    try:
                        mid = self.telegram.document(png, f"{state['data']['kind']}-{session_id}.png")
                    except DeliveryUncertain:
                        state['status'] = 'uncertain'
                        self.store.write('session', state)
                        self.telegram.prompt('Invio incerto: controlla se il PNG è arrivato. /reinvia solo se manca, altrimenti /annulla.')
                    except TelegramError:
                        state['status'] = 'failed'
                        self.store.write('session', state)
                        self.telegram.prompt('Invio rifiutato da Telegram. /reinvia per riprovare.')
                    else:
                        state.update(status='completed', message_id=mid)
                        self.store.write('session', state)
                        self.telegram.prompt('PNG originale inviato. /grafica per un’altra immagine.')
        state = self.store.read('session')
        if state.get('status') == 'ready' and self.worker is None:
            state['status'] = 'rendering'
            self.store.write('session', state)
            data, sid = copy.deepcopy(state['data']), state['id']
            def work():
                try:
                    self.results.put((sid, self.renderer.render(data), None))
                except Exception as exc:
                    # Never echo raw HTTP errors, URLs or credentials to Telegram.
                    self.results.put((sid, None, type(exc).__name__))
            self.worker = threading.Thread(target=work, daemon=True)
            self.worker.start()

    def run(self, duration=1800):
        deadline = time.monotonic() + min(1800, max(1, duration))
        self.restore()
        self.telegram.prompt('Generatore attivo per 30 minuti. Scrivi /grafica. Nessun riavvio automatico.')
        failures = 0
        while not self.stopped and time.monotonic() < deadline:
            try:
                self.conversations()
                self.rendering()
                self.receive()
                failures = 0
            except Exception as exc:
                failures += 1
                print(f'WARN MANUAL: {type(exc).__name__}; tentativo {failures}', flush=True)
                if failures >= 5:
                    raise RuntimeError('Generatore fermato dopo errori ripetuti') from None
                time.sleep(min(2 * failures, 10))
        # No successor: the next run can only be started manually.
        state = self.store.read('session')
        if state.get('status') == 'rendering':
            state['status'] = 'ready'
            self.store.write('session', state)
        self.telegram.prompt('Generatore terminato. Per usarlo ancora, avvia manualmente il workflow. Le richieste incomplete sono conservate.')


def main():
    from .config import resources
    from .catalog import Catalog
    from .conversation import Wizard
    from .render import Renderer
    store, api, tokens = resources()
    telegram = Telegram(os.environ['TELEGRAM_TOKEN'], os.environ['TELEGRAM_TO_BOT'])
    owner = telegram.validate_private_chat()
    configured_owner = os.getenv('MANUAL_GRAPHICS_OWNER_ID')
    if configured_owner and str(owner) != configured_owner:
        raise RuntimeError('Owner diverso dalla chat privata configurata')
    coordinator = Coordinator(store, os.environ['GITHUB_RUN_ID'], api.run_active)
    service = Service(store, telegram, Wizard(Catalog()), Renderer(tokens.get), owner, owner)
    def stop(*_):
        service.stopped = True
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    coordinator.request()
    try:
        deadline = time.monotonic() + 180
        while not coordinator.ready(api.active_live_runs()):
            if service.stopped or time.monotonic() > deadline:
                raise RuntimeError('Il live non ha confermato il passaggio Telegram; avvio annullato in sicurezza')
            time.sleep(3)
        state = store.read('receiver')
        ack = store.read('ack')
        state['offset'] = max(int(state.get('offset', 0)), int(ack.get('offset', 0)))
        store.write('receiver', state)
        service.run()
    finally:
        coordinator.finish(store.read('receiver').get('offset', 0))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'ERROR MANUAL: {type(exc).__name__}. Nessun riavvio automatico.', flush=True)
        raise SystemExit(1)
