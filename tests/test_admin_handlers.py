import unittest

from admin.admin_handlers import (
    _admin_role_label,
    _diff_line,
    _extract_quest_points,
    _format_user_ref,
    _int_text,
    _short_text,
    _yes_no,
)


class ExtractQuestPointsTests(unittest.TestCase):
    def test_prefers_points_field(self):
        row = {"points": 5, "points_reply": 1}
        self.assertEqual(_extract_quest_points(row), 5)

    def test_falls_back_to_legacy_points_reply(self):
        row = {"points_reply": 4}
        self.assertEqual(_extract_quest_points(row), 4)

    def test_returns_zero_for_invalid_value(self):
        self.assertEqual(_extract_quest_points({"points": "bad"}), 0)
        self.assertEqual(_extract_quest_points({}), 0)


class AdminEventFormattingTests(unittest.TestCase):
    def test_short_text_flattens_whitespace(self):
        self.assertEqual(_short_text("  hello \n world  "), "hello world")

    def test_diff_line_returns_none_when_same(self):
        self.assertIsNone(_diff_line("Баллы", 2, 2, formatter=_int_text))

    def test_diff_line_formats_old_to_new(self):
        self.assertEqual(
            _diff_line("Баллы", 1, 3, formatter=_int_text),
            "• Баллы: 1 → 3",
        )

    def test_diff_line_uses_single_arrow_for_new_value(self):
        self.assertEqual(
            _diff_line("Текст", None, "новое"),
            "• Текст: → новое",
        )

    def test_format_user_ref_prefers_username(self):
        row = {"username": "fastnet", "display_name": "Ivan"}
        self.assertEqual(_format_user_ref(10, row), "@fastnet (id=10)")

    def test_format_user_ref_falls_back_to_display_name(self):
        row = {"display_name": "Ivan Kostin"}
        self.assertEqual(_format_user_ref(11, row), "Ivan Kostin (id=11)")

    def test_helpers_for_labels(self):
        self.assertEqual(_yes_no(True), "да")
        self.assertEqual(_yes_no(False), "нет")
        self.assertEqual(_admin_role_label("owner"), "owner")
        self.assertEqual(_admin_role_label(""), "нет роли")


if __name__ == "__main__":
    unittest.main()
