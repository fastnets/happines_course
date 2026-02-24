import unittest
from types import SimpleNamespace

from scheduling.worker import _send_quest_message


class _DummyBot:
    def __init__(self, fail_photo=False):
        self.fail_photo = fail_photo
        self.photo_calls = []
        self.message_calls = []

    async def send_photo(self, **kwargs):
        self.photo_calls.append(kwargs)
        if self.fail_photo:
            raise RuntimeError("photo failed")
        return SimpleNamespace(message_id=1001)

    async def send_message(self, **kwargs):
        self.message_calls.append(kwargs)
        return SimpleNamespace(message_id=2001)


class WorkerQuestPhotoTests(unittest.IsolatedAsyncioTestCase):
    async def test_prefers_send_photo_when_photo_exists(self):
        bot = _DummyBot()
        quest = {"prompt": "Сделай 10 приседаний", "photo_file_id": "file_123"}

        msg = await _send_quest_message(bot, user_id=42, day_index=3, quest=quest, kb=object())

        self.assertEqual(msg.message_id, 1001)
        self.assertEqual(len(bot.photo_calls), 1)
        self.assertEqual(len(bot.message_calls), 0)

    async def test_falls_back_to_send_message_when_photo_fails(self):
        bot = _DummyBot(fail_photo=True)
        quest = {"prompt": "Сделай 10 приседаний", "photo_file_id": "file_123"}

        msg = await _send_quest_message(bot, user_id=42, day_index=3, quest=quest, kb=object())

        self.assertEqual(msg.message_id, 2001)
        self.assertEqual(len(bot.photo_calls), 1)
        self.assertEqual(len(bot.message_calls), 1)

    async def test_uses_send_message_when_photo_absent(self):
        bot = _DummyBot()
        quest = {"prompt": "Сделай 10 приседаний"}

        msg = await _send_quest_message(bot, user_id=42, day_index=3, quest=quest, kb=object())

        self.assertEqual(msg.message_id, 2001)
        self.assertEqual(len(bot.photo_calls), 0)
        self.assertEqual(len(bot.message_calls), 1)


if __name__ == "__main__":
    unittest.main()
