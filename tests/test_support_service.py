import unittest

from core.support_service import SupportService


class DummyRepo:
    def __init__(self):
        self.items = {}
        self.seq = 0

    def create(self, user_id: int, question_text: str):
        self.seq += 1
        row = {
            "id": self.seq,
            "user_id": int(user_id),
            "status": "open",
            "question_text": question_text,
            "admin_id": None,
            "admin_reply": None,
        }
        self.items[self.seq] = row
        return dict(row)

    def list_tickets(self, status="open", limit=20):
        rows = list(self.items.values())
        if status:
            rows = [r for r in rows if r.get("status") == status]
        rows.sort(key=lambda r: int(r["id"]), reverse=True)
        return [dict(r) for r in rows[: int(limit)]]

    def get(self, ticket_id: int):
        row = self.items.get(int(ticket_id))
        return dict(row) if row else None

    def close_with_reply(self, ticket_id: int, admin_id: int, admin_reply: str):
        row = self.items.get(int(ticket_id))
        if not row or row.get("status") != "open":
            return None
        row["status"] = "closed"
        row["admin_id"] = int(admin_id)
        row["admin_reply"] = admin_reply
        return dict(row)

    def close(self, ticket_id: int, admin_id: int):
        row = self.items.get(int(ticket_id))
        if not row or row.get("status") != "open":
            return None
        row["status"] = "closed"
        row["admin_id"] = int(admin_id)
        return dict(row)


class SupportServiceTests(unittest.TestCase):
    def _svc(self):
        svc = SupportService.__new__(SupportService)
        svc.settings = object()
        svc.repo = DummyRepo()
        return svc

    def test_create_and_list_open(self):
        svc = self._svc()
        self.assertIsNone(svc.create_ticket(1, "   "))
        t1 = svc.create_ticket(1, "Нужна помощь")
        t2 = svc.create_ticket(2, "Проблема с заданием")
        self.assertEqual(int(t1["id"]), 1)
        self.assertEqual(int(t2["id"]), 2)

        rows = svc.list_open(limit=10)
        self.assertEqual([int(r["id"]) for r in rows], [2, 1])

    def test_reply_and_close_is_idempotent_for_closed_ticket(self):
        svc = self._svc()
        t = svc.create_ticket(5, "test")
        tid = int(t["id"])

        first = svc.reply_and_close(tid, admin_id=900, reply_text="Ответ")
        second = svc.reply_and_close(tid, admin_id=900, reply_text="Второй ответ")

        self.assertIsNotNone(first)
        self.assertEqual(first["status"], "closed")
        self.assertEqual(first["admin_reply"], "Ответ")
        self.assertIsNone(second)


if __name__ == "__main__":
    unittest.main()

