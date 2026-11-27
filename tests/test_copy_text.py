import unittest
from unittest import mock

from livescore.telegram import copy_text


FT = ("<b>FINE PARTITA 🏁</b>\n\nJuventus <b>4</b>-1 Omonia\n"
      "⚽️ <i>37' Cambiaso, 43' Ekhator, 68' Conceição, 73' Boga // 15' Satka</i>\n\n🇪🇺 #JuveOmonia")


class CopyTextTest(unittest.TestCase):
    def test_x_like_profile(self):
        self.assertEqual(copy_text.x_text(FT, 'Juventus', 'Omonia'),
                         "FINE PARTITA 🏁\n\n#Juventus 4-1 #Omonia\n"
                         "⚽️ 37' #Cambiaso, 43' #Ekhator, 68' #Conceição, 73' #Boga // 15' #Satka\n\n🇪🇺 #JuveOmonia")

    def test_names_with_spaces_initials_and_own_goal(self):
        text = ("<b>FINE PRIMO TEMPO 🏁</b>\n\nAZ Alkmaar 0-<b>2 Juventus</b>\n"
                "⚽️ <i>19', 45+1' Kolo Muani, 37' I. Saibari (Autogol)</i>\n\n🇪🇺 #AZJuve")
        self.assertEqual(copy_text.x_text(text, 'AZ Alkmaar', 'Juventus'),
                         "FINE PRIMO TEMPO 🏁\n\n#AZAlkmaar 0-2 #Juventus\n"
                         "⚽️ 19', 45+1' #KoloMuani, 37' #Saibari (Autogol)\n\n🇪🇺 #AZJuve")

    def test_no_goals_and_custom_emoji(self):
        text = ('<b>FINE PRIMO TEMPO 🏁</b>\n\nJuventus 0-0 Venezia\n\n'
                '<tg-emoji emoji-id="1">🇮🇹</tg-emoji> #JuveVenezia')
        self.assertEqual(copy_text.x_text(text, 'Juventus', 'Venezia'),
                         'FINE PRIMO TEMPO 🏁\n\n#Juventus 0-0 #Venezia\n\n🇮🇹 #JuveVenezia')
        self.assertEqual(copy_text.plain(text), 'FINE PRIMO TEMPO 🏁\n\nJuventus 0-0 Venezia\n\n🇮🇹 #JuveVenezia')

    def test_telegram_text_then_x_box_as_reply(self):
        post = mock.Mock(return_value=mock.Mock(status_code=200, json=lambda: {'result': {'message_id': 55}}))
        text = FT.replace('🇪🇺', '<tg-emoji emoji-id="1">🇪🇺</tg-emoji>')
        copy_text.send(post, '123', text, 'Juventus', 'Omonia')
        tg, xb = [c.kwargs['payload'] for c in post.call_args_list]
        self.assertEqual((tg['chat_id'], tg['text']), ('123', text))        # come sul canale, senza scritte
        self.assertTrue(xb['text'].startswith('FINE PARTITA 🏁\n\n#Juventus 4-1 #Omonia'))
        self.assertEqual(xb['reply_parameters']['message_id'], 55)          # X in risposta

    def test_no_chat_no_messages_and_errors_never_raise(self):
        post = mock.Mock(side_effect=RuntimeError('rete giù'))
        copy_text.send(post, '', FT, 'Juventus', 'Omonia')
        post.assert_not_called()
        copy_text.send(post, '123', FT, 'Juventus', 'Omonia')     # non solleva


if __name__ == '__main__':
    unittest.main()
