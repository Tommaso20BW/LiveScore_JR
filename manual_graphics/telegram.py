"""Telegram transport; document output is always the configured Bot JR chat."""
import json
from urllib.parse import urlparse

import requests


class TelegramError(RuntimeError):
    pass


class DeliveryUncertain(TelegramError):
    pass


def authorized(update, owner_id, chat_id):
    callback = update.get('callback_query') or {}
    message = callback.get('message') or update.get('message') or {}
    sender = callback.get('from') or message.get('from') or {}
    chat = message.get('chat') or {}
    return (str(sender.get('id')) == str(owner_id)
            and str(chat.get('id')) == str(chat_id)
            and chat.get('type') == 'private')


class Telegram:
    def __init__(self, token, chat_id, session=None):
        if not token or not chat_id:
            raise TelegramError('Configurazione Telegram mancante')
        self.base = f'https://api.telegram.org/bot{token}/'
        self.chat_id = str(chat_id)
        self.session = session or requests.Session()

    def call(self, method, data=None, files=None, timeout=25):
        try:
            r = self.session.post(self.base + method, data=data, files=files, timeout=timeout)
            if r.status_code >= 500 and method == 'sendDocument':
                raise DeliveryUncertain('Invio PNG con esito incerto')
            if r.status_code != 200:
                raise TelegramError(f'{method}: HTTP {r.status_code}')
            value = r.json()
            if not value.get('ok'):
                raise TelegramError(f'{method}: richiesta rifiutata')
            return value['result']
        except (requests.RequestException, ValueError, KeyError, TypeError):
            if method == 'sendDocument':
                raise DeliveryUncertain('Invio PNG con esito incerto') from None
            raise TelegramError(f'{method}: connessione non disponibile') from None

    def validate_private_chat(self):
        chat = self.call('getChat', {'chat_id': self.chat_id})
        if chat.get('type') != 'private' or str(chat.get('id')) != self.chat_id:
            raise TelegramError('Il generatore richiede la chat privata Bot JR')
        return int(chat['id'])

    def poll(self, offset):
        return self.call('getUpdates', {'offset': offset, 'timeout': 10,
            'allowed_updates': '["message","callback_query"]'}, timeout=15)

    def prompt(self, text, keyboard=None):
        data = {'chat_id': self.chat_id, 'text': text, 'disable_web_page_preview': 'true'}
        if keyboard:
            data['reply_markup'] = json.dumps(keyboard)
        return self.call('sendMessage', data)['message_id']

    def webapp_launcher(self, url):
        parsed = urlparse(str(url).strip())
        if parsed.scheme != 'https' or not parsed.netloc:
            raise TelegramError('URL Mini App non HTTPS')
        keyboard = {
            'keyboard': [[{
                'text': '🎨 Apri generatore',
                'web_app': {'url': str(url).strip()},
            }]],
            'resize_keyboard': True,
            'is_persistent': True,
            'input_field_placeholder': 'Apri il generatore grafico',
        }
        return self.prompt(
            '🎨 Generatore grafiche attivo per 30 minuti. Usa il pulsante qui sotto.',
            keyboard,
        )

    def remove_keyboard(self):
        return self.prompt('Chiusura generatore…', {'remove_keyboard': True})

    def delete(self, message_id):
        return self.call('deleteMessage', {
            'chat_id': self.chat_id,
            'message_id': int(message_id),
        })

    def answer(self, callback_id, text=''):
        return self.call('answerCallbackQuery', {'callback_query_id': callback_id, 'text': text[:180]})

    def document(self, png, filename='grafica.png'):
        if not png.startswith(b'\x89PNG\r\n\x1a\n'):
            raise TelegramError('Il renderer non ha prodotto un PNG')
        result = self.call('sendDocument', {'chat_id': self.chat_id},
            files={'document': (filename, png, 'image/png')}, timeout=60)
        try:
            return int(result['message_id'])
        except (KeyError, TypeError, ValueError):
            raise DeliveryUncertain('Telegram non ha confermato il messaggio PNG') from None
