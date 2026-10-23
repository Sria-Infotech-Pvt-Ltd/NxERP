import frappe
from frappe.tests.utils import FrappeTestCase

from helpdesk.api.theme import set_desk_theme


class TestDeskTheme(FrappeTestCase):
    def tearDown(self):
        frappe.set_user("Administrator")

    def test_saves_valid_theme_on_session_user(self):
        set_desk_theme("Dark")
        self.assertEqual(
            frappe.db.get_value("User", "Administrator", "desk_theme"), "Dark"
        )

        set_desk_theme("Automatic")
        self.assertEqual(
            frappe.db.get_value("User", "Administrator", "desk_theme"), "Automatic"
        )

    def test_rejects_unknown_theme(self):
        self.assertRaises(frappe.ValidationError, set_desk_theme, "Solarized")

    def test_guest_is_ignored(self):
        frappe.set_user("Guest")
        set_desk_theme("Dark")
        self.assertNotEqual(frappe.db.get_value("User", "Guest", "desk_theme"), "Dark")
