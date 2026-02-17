from __future__ import annotations

from entity.repositories.support_tickets_repo import SupportTicketsRepo


class SupportService:
    def __init__(self, db, settings):
        self.settings = settings
        self.repo = SupportTicketsRepo(db)

    def create_ticket(self, user_id: int, question_text: str) -> dict | None:
        text = (question_text or "").strip()
        if not text:
            return None
        text = text[:2000]
        return self.repo.create(user_id=user_id, question_text=text)

    def list_open(self, limit: int = 20) -> list[dict]:
        return self.repo.list_tickets(status="open", limit=limit)

    def list_all(self, limit: int = 20) -> list[dict]:
        return self.repo.list_tickets(status=None, limit=limit)

    def get(self, ticket_id: int) -> dict | None:
        return self.repo.get(ticket_id)

    def reply_and_close(self, ticket_id: int, admin_id: int, reply_text: str) -> dict | None:
        text = (reply_text or "").strip()
        if not text:
            return None
        text = text[:2000]
        return self.repo.close_with_reply(ticket_id=ticket_id, admin_id=admin_id, admin_reply=text)

    def close(self, ticket_id: int, admin_id: int) -> dict | None:
        return self.repo.close(ticket_id=ticket_id, admin_id=admin_id)

