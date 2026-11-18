import re
import unittest

from helpdesk import theme_tokens

HEX = re.compile(r"^#[0-9a-f]{6}$")


class TestThemeTokens(unittest.TestCase):
    """The generated palette module that server-side code (emails, reports, charts) reads."""

    def test_email_colors_are_palette_hex_in_both_modes(self):
        for mode in ("light", "dark"):
            for role, value in theme_tokens.EMAIL[mode].items():
                self.assertRegex(value, HEX, f"EMAIL[{mode}][{role}]")

    def test_message_panel_is_paper_in_light_mode(self):
        self.assertEqual(theme_tokens.EMAIL["light"]["panelBg"], "#fcfcfb")

    def test_chart_series_lead_with_the_accent(self):
        for mode in ("light", "dark"):
            series = theme_tokens.CHART_SERIES[mode]
            self.assertGreaterEqual(len(series), 8)
            self.assertEqual(series[0], "#faa114")

    def test_stored_email_templates_use_palette_values(self):
        from helpdesk.helpdesk.doctype.hd_settings.helpers import get_default_email_content

        panel = theme_tokens.EMAIL["light"]
        for kind in ("reply_to_agents", "reply_via_agent"):
            html = get_default_email_content(kind)
            self.assertIn(panel["panelBg"], html, kind)
            self.assertNotIn("#f3f5f8", html, kind)
