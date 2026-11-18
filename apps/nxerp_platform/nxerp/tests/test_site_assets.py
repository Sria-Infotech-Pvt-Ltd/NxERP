"""Static guards on the public site's CSS and templates (no server needed).

1. No colour literal: only palette tokens from nxerp-theme.css. A hex, rgb(), hsl() or a colour name in a NEW or CHANGED
   stylesheet, template or inline style fails. The only literals anywhere in the platform are the documented icon data-URIs
   in nxerp-login.css and the film-grain data-URI in nxerp-platform.css (neither is in the files checked here).
2. The pre-paint theme script sits in <head> before any stylesheet, so the theme is set before the first paint.
3. The site stylesheet only adds rules: it never redefines the launcher's or the no-access page's classes.
"""

import re
from pathlib import Path

import frappe
from frappe.tests import IntegrationTestCase

NXERP = Path(frappe.get_app_path("nxerp"))

# files that belong to the public site (new in Phase 1)
CSS_FILES = [NXERP / "public/css/nxerp-site.css", NXERP / "public/css/nxerp-onboarding.css"]
HTML_FILES = [
	*sorted((NXERP / "templates/includes/nxdesk").glob("*.html")),
	NXERP / "www/nxerp/home.html",
	NXERP / "www/nxerp/products.html",
	NXERP / "www/nxerp/product.html",
	NXERP / "www/nxerp/signup.html",
	NXERP / "www/nxerp/welcome.html",
	NXERP / "www/nxerp/get_started.html",
	NXERP / "www/nxerp/page.html",
	NXERP / "www/nxerp/no-access.html",
]

# Documented exceptions: (file name, literal). Empty on purpose.
ALLOWED_LITERALS: tuple = ()

NAMED_COLOURS = set(
	"""aliceblue antiquewhite aqua aquamarine azure beige bisque black blanchedalmond blue blueviolet brown burlywood cadetblue
chartreuse chocolate coral cornflowerblue cornsilk crimson cyan darkblue darkcyan darkgoldenrod darkgray darkgreen darkgrey
darkkhaki darkmagenta darkolivegreen darkorange darkorchid darkred darksalmon darkseagreen darkslateblue darkslategray
darkslategrey darkturquoise darkviolet deeppink deepskyblue dimgray dimgrey dodgerblue firebrick floralwhite forestgreen
fuchsia gainsboro ghostwhite gold goldenrod gray green greenyellow grey honeydew hotpink indianred indigo ivory khaki lavender
lavenderblush lawngreen lemonchiffon lightblue lightcoral lightcyan lightgoldenrodyellow lightgray lightgreen lightgrey
lightpink lightsalmon lightseagreen lightskyblue lightslategray lightslategrey lightsteelblue lightyellow lime limegreen linen
magenta maroon mediumaquamarine mediumblue mediumorchid mediumpurple mediumseagreen mediumslateblue mediumspringgreen
mediumturquoise mediumvioletred midnightblue mintcream mistyrose moccasin navajowhite navy oldlace olive olivedrab orange
orangered orchid palegoldenrod palegreen paleturquoise palevioletred papayawhip peachpuff peru pink plum powderblue purple
rebeccapurple red rosybrown royalblue saddlebrown salmon sandybrown seagreen seashell sienna silver skyblue slateblue
slategray slategrey snow springgreen steelblue tan teal thistle tomato turquoise violet wheat white whitesmoke yellow
yellowgreen""".split()
)

HEX = re.compile(r"#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3,4})(?![\w-])")
COLOUR_FUNCTION = re.compile(r"\b(?:rgb|rgba|hsl|hsla|hwb|lab|lch|oklab|oklch)\(", re.I)
WORD = re.compile(r"(?<![\w#.-])([a-zA-Z]+)(?![\w(-])")


def _css_declarations(css: str) -> list:
	"""The text inside every {...} block, without comments, url(...) and quoted strings."""
	css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
	css = re.sub(r"url\([^)]*\)", "url()", css)
	css = re.sub(r'"[^"]*"|\'[^\']*\'', '""', css)
	return re.findall(r"\{([^{}]*)\}", css)


def colour_literals(text: str, is_css: bool) -> list:
	"""Every literal colour in `text`. For HTML only style attributes, <style> blocks and SVG paint attributes count for names."""
	found = []
	scan = re.sub(r'href="#[^"]*"', 'href=""', text)  # in-page anchors such as #main are not colours
	found += HEX.findall(scan)
	found += COLOUR_FUNCTION.findall(scan)
	if is_css:
		chunks = _css_declarations(text)
	else:
		chunks = re.findall(r'style="([^"]*)"', text) + re.findall(
			r"<style[^>]*>(.*?)</style>", text, flags=re.S
		)
		chunks += re.findall(r'(?:fill|stroke|stop-color|color)="([^"]*)"', text)
	for chunk in chunks:
		found += [w for w in WORD.findall(chunk) if w.lower() in NAMED_COLOURS]
	return found


class TestSiteAssets(IntegrationTestCase):
	def test_the_files_exist(self):
		for path in (*CSS_FILES, *HTML_FILES):
			self.assertTrue(path.is_file(), path)
		self.assertGreaterEqual(len(HTML_FILES), 12)

	def test_no_colour_literals_in_the_public_sites_css_and_templates(self):
		for path in (*CSS_FILES, *HTML_FILES):
			found = [
				f
				for f in colour_literals(path.read_text(encoding="utf-8"), path.suffix == ".css")
				if (path.name, f) not in ALLOWED_LITERALS
			]
			self.assertEqual(found, [], f"{path.relative_to(NXERP)} uses literal colours: use palette tokens")

	def test_the_colour_check_catches_what_it_is_for(self):
		for bad in (
			"a { color: #fff; }",
			"a { color: #12345678; }",
			"a { background: rgb(1 2 3); }",
			"a { color: hsl(0 0% 0%); }",
			"a { color: red; }",
			"a { border: 1px solid Black; }",
		):
			self.assertTrue(colour_literals(bad, True), bad)
		self.assertTrue(colour_literals('<p style="color: tomato">x</p>', False))
		self.assertTrue(colour_literals('<svg stroke="#abc"></svg>', False))
		for fine in (
			"a { color: var(--ink-gray-9); background: color-mix(in srgb, var(--brand-amber) 14%, transparent); }",
			"a { border: 1px solid var(--red-600); color: currentColor; }",
			"a { background-image: url(\"data:image/svg+xml,%3Csvg fill='%23ccc'/%3E\"); }",
			".nxp-red-note { margin: 0; }",
		):
			self.assertEqual(colour_literals(fine, True), [], fine)
		self.assertEqual(colour_literals('<a href="#main">skip</a>', False), [])

	def test_the_theme_script_runs_before_any_stylesheet(self):
		head = (NXERP / "templates/includes/nxdesk/head.html").read_text(encoding="utf-8")
		self.assertIn('setAttribute("data-theme"', head)
		self.assertLess(head.index('setAttribute("data-theme"'), head.index('rel="stylesheet"'))
		self.assertLess(head.index("<script>"), head.index('rel="stylesheet"'))
		# the same key and values as the launcher, the login page and the apps
		self.assertIn('localStorage.getItem("theme")', head)

	def test_every_public_page_pulls_in_the_shared_partials(self):
		for name in ("home", "products", "product"):
			html = (NXERP / f"www/nxerp/{name}.html").read_text(encoding="utf-8")
			for partial in ("head", "header", "footer", "scripts"):
				self.assertIn(f"nxdesk/{partial}.html", html, f"{name} must include {partial}")
			self.assertEqual(html.count("<h1"), 1, name)

	def test_the_site_stylesheet_only_adds_rules(self):
		"""Selectors of the launcher and no-access page (nxerp-platform.css) are never redefined here, except where a
		compound selector adds a new class (`.nxp-cta.nxp-button`)."""
		platform = (NXERP / "public/css/nxerp-platform.css").read_text(encoding="utf-8")
		site = (NXERP / "public/css/nxerp-site.css").read_text(encoding="utf-8")
		strip = lambda css: re.sub(r"/\*.*?\*/", "", css, flags=re.S)  # noqa: E731
		defined = {
			s.strip()
			for s in re.findall(r"([^{}]+)\{", strip(platform))
			if not s.strip().startswith(("@", "from", "to"))
		}
		redefined = {s.strip() for s in re.findall(r"([^{}]+)\{", strip(site))} & defined
		self.assertEqual(redefined, set(), "nxerp-site.css must not redefine nxerp-platform.css selectors")
