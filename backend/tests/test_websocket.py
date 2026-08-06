import unittest

from app.api.ws import ConnectionManager, _user_id_from_channel


class FakeWebSocket:
    def __init__(self, fail: bool = False):
        self.fail = fail
        self.messages: list[dict] = []

    async def send_json(self, message: dict) -> None:
        if self.fail:
            raise RuntimeError("connection closed")
        self.messages.append(message)


class ConnectionManagerTests(unittest.IsolatedAsyncioTestCase):
    async def test_same_user_can_receive_updates_on_multiple_connections(self):
        manager = ConnectionManager()
        first = FakeWebSocket()
        second = FakeWebSocket()
        manager.connect(first, "user-1")
        manager.connect(second, "user-1")

        await manager.send_to_user("user-1", {"type": "job_update"})

        self.assertEqual(first.messages, [{"type": "job_update"}])
        self.assertEqual(second.messages, [{"type": "job_update"}])

    async def test_failed_connection_is_removed_without_affecting_others(self):
        manager = ConnectionManager()
        healthy = FakeWebSocket()
        failed = FakeWebSocket(fail=True)
        manager.connect(healthy, "user-1")
        manager.connect(failed, "user-1")

        await manager.send_to_user("user-1", {"type": "job_update"})

        self.assertEqual(healthy.messages, [{"type": "job_update"}])
        self.assertEqual(manager.active_connections["user-1"], {healthy})


class ChannelParsingTests(unittest.TestCase):
    def test_user_id_is_extracted_from_expected_channel(self):
        self.assertEqual(_user_id_from_channel("ws:job_updates:user-1"), "user-1")

    def test_unrelated_or_empty_channel_is_ignored(self):
        self.assertIsNone(_user_id_from_channel("other:user-1"))
        self.assertIsNone(_user_id_from_channel("ws:job_updates:"))


if __name__ == "__main__":
    unittest.main()
