"""Explicit polling handoff; live remains autonomous when manual is stopped."""
import time
import uuid


class Coordinator:
    def __init__(self, store, run_id, run_active):
        self.store, self.run_id, self.run_active = store, str(run_id), run_active
        self.request_id = uuid.uuid4().hex

    def request(self):
        self.store.write('control', {'run_id': self.run_id, 'request_id': self.request_id,
                                    'active': True, 'started': time.time()})

    def ready(self, live_runs):
        ack = self.store.read('ack')
        return not live_runs or (len(live_runs) == 1
            and str(ack.get('manual_run')) == self.run_id
            and ack.get('request_id') == self.request_id
            and str(ack.get('live_run')) == str(live_runs[0]))

    def live_paused(self, offset):
        control = self.store.read('control')
        manual_id = str(control.get('run_id') or '')
        if not control.get('active') or not manual_id or not self.run_active(manual_id):
            return False
        ack = self.store.read('ack')
        value = {'manual_run': manual_id, 'live_run': self.run_id,
                 'request_id': control.get('request_id'), 'offset': int(offset or 0)}
        if ack != value:
            self.store.write('ack', value)
        return True

    def finish(self, offset):
        state = self.store.read('receiver')
        state['offset'] = max(int(state.get('offset', 0)), int(offset or 0))
        self.store.write('receiver', state)
        self.store.write('control', {'run_id': self.run_id, 'active': False})
