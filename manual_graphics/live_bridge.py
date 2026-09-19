"""Replace only the live Telegram input and Canva credential provider."""
import os
from .coordination import Coordinator


class Response:
    status_code = 200
    def __init__(self, updates):
        self.updates = updates
    def json(self):
        return {'ok': True, 'result': self.updates}
    def raise_for_status(self):
        return None


def bridge_poll(store, coordinator, original_poll, data):
    offset = int(data.get('offset') or 0)
    paused = coordinator.live_paused(offset)
    state = store.read('receiver')
    queued = [u for u in state.get('kit', []) if int(u['update_id']) >= offset]
    # Ack belongs to the live only. Advancing it means the previous batch was
    # handled by the existing runtime, whose offset was passed in this call.
    ack = store.read('ack')
    if offset > int(ack.get('offset', 0)):
        ack['offset'] = offset
        store.write('ack', ack)
    if queued:
        return Response(queued)
    if paused:
        return Response([])
    args = dict(data)
    args['offset'] = max(offset, int(state.get('offset', 0)))
    return original_poll(args)


def install(bot, runtime):
    from .config import resources
    store, api, tokens = resources()
    coordinator = Coordinator(store, os.environ['GITHUB_RUN_ID'], api.run_active)
    original = bot._tg_post

    def wrapped(method, *args, **kwargs):
        if method != 'getUpdates':
            return original(method, *args, **kwargs)
        data = kwargs.get('data') or kwargs.get('payload') or {}
        try:
            return bridge_poll(store, coordinator,
                lambda values: original('getUpdates', data=values, timeout=5), data)
        except Exception as exc:
            # Fail closed: an unconfirmed handoff must never create two readers.
            bot.log_line('WARN', 'MANUAL', f'Lettura condivisa non disponibile: {type(exc).__name__}')
            return Response([])

    def token():
        try:
            return tokens.get()
        except Exception as exc:
            bot.log_line('WARN', 'CANVA', f'Token condiviso non disponibile: {type(exc).__name__}')
            return None

    bot._tg_post = wrapped
    bot.get_valid_token = token
    # A discovery-time drain would discard forwarded callbacks or wizard input.
    runtime._drain_old_callbacks = lambda: None
