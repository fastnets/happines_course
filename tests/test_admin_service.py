import unittest

from admin.admin_service import AdminService


class DummyAdminsRepo:
    def __init__(self):
        self.roles: dict[int, str] = {}

    def is_admin(self, user_id: int) -> bool:
        return int(user_id) in self.roles

    def is_owner(self, user_id: int) -> bool:
        return self.roles.get(int(user_id)) == "owner"

    def add(self, user_id: int):
        uid = int(user_id)
        if uid not in self.roles:
            self.roles[uid] = "admin"

    def upsert(self, user_id: int, role: str = "admin"):
        uid = int(user_id)
        self.roles[uid] = "owner" if str(role).strip().lower() == "owner" else "admin"

    def remove(self, user_id: int):
        self.roles.pop(int(user_id), None)

    def count_owners(self) -> int:
        return sum(1 for role in self.roles.values() if role == "owner")

    def list_user_ids(self) -> list[int]:
        return sorted(self.roles.keys())

    def list_admins(self) -> list[dict]:
        out = []
        for uid in sorted(self.roles.keys()):
            out.append({"user_id": uid, "role": self.roles[uid], "created_at": None})
        return out


class DummySettings:
    def __init__(self, admin_tg_ids=None, owner_tg_id=None):
        self.admin_tg_ids = list(admin_tg_ids or [])
        self.owner_tg_id = owner_tg_id


class AdminServiceOwnerTests(unittest.TestCase):
    def _svc(self, env_admins=None, owner_uid=None):
        svc = AdminService.__new__(AdminService)
        svc.db = object()
        svc.settings = DummySettings(env_admins, owner_uid)
        svc.admins = DummyAdminsRepo()
        svc.q = object()
        return svc

    def test_seed_creates_first_owner_from_env(self):
        svc = self._svc([1001, 1002])
        svc.seed_admins_from_settings()
        self.assertTrue(svc.is_admin(1001))
        self.assertTrue(svc.is_admin(1002))
        self.assertTrue(svc.is_owner(1001))
        self.assertFalse(svc.is_owner(1002))

    def test_owner_can_grant_and_remove_admin(self):
        svc = self._svc([1001])
        svc.seed_admins_from_settings()

        ok, _ = svc.grant_admin(1001, 2001)
        self.assertTrue(ok)
        self.assertTrue(svc.is_admin(2001))
        self.assertFalse(svc.is_owner(2001))

        ok, _ = svc.remove_admin(1001, 2001)
        self.assertTrue(ok)
        self.assertFalse(svc.is_admin(2001))

    def test_grant_admin_does_not_demote_owner(self):
        svc = self._svc([1001])
        svc.seed_admins_from_settings()
        ok, msg = svc.grant_admin(1001, 1001)
        self.assertFalse(ok)
        self.assertIn("уже owner", msg)
        self.assertTrue(svc.is_owner(1001))

    def test_non_owner_cannot_manage_admins(self):
        svc = self._svc([1001])
        svc.seed_admins_from_settings()
        svc.grant_admin(1001, 1002)

        ok, msg = svc.grant_admin(1002, 3001)
        self.assertFalse(ok)
        self.assertIn("Только owner", msg)

    def test_cannot_demote_or_remove_last_owner(self):
        svc = self._svc([1001])
        svc.seed_admins_from_settings()

        ok_demote, msg_demote = svc.demote_owner_to_admin(1001, 1001)
        ok_remove, msg_remove = svc.remove_admin(1001, 1001)

        self.assertFalse(ok_demote)
        self.assertIn("последнего owner", msg_demote)
        self.assertFalse(ok_remove)
        self.assertIn("последнего owner", msg_remove)

    def test_can_demote_owner_when_another_owner_exists(self):
        svc = self._svc([1001])
        svc.seed_admins_from_settings()
        ok, _ = svc.grant_owner(1001, 1002)
        self.assertTrue(ok)
        self.assertTrue(svc.is_owner(1002))

        ok, _ = svc.demote_owner_to_admin(1001, 1002)
        self.assertTrue(ok)
        self.assertTrue(svc.is_admin(1002))
        self.assertFalse(svc.is_owner(1002))

    def test_set_role_switches_between_owner_and_admin(self):
        svc = self._svc([1001])
        svc.seed_admins_from_settings()
        svc.grant_admin(1001, 2001)

        ok_owner, _ = svc.set_role(1001, 2001, "owner")
        self.assertTrue(ok_owner)
        self.assertTrue(svc.is_owner(2001))

        ok_admin, _ = svc.set_role(1001, 2001, "admin")
        self.assertTrue(ok_admin)
        self.assertTrue(svc.is_admin(2001))
        self.assertFalse(svc.is_owner(2001))

    def test_seed_respects_owner_tg_id_from_settings(self):
        svc = self._svc([2002], owner_uid=1001)
        svc.seed_admins_from_settings()
        self.assertTrue(svc.is_owner(1001))
        self.assertTrue(svc.is_admin(2002))


if __name__ == "__main__":
    unittest.main()
