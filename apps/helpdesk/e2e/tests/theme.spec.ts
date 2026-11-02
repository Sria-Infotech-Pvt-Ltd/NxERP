import { tokens } from "../../desk/src/theme/generated/tokens";
import { expect, test, usePersona } from "../helpers/fixtures";
import { emailOf } from "../helpers/personas";

usePersona("agent");

const SAMPLE = [
  "surface-base",
  "surface-gray-2",
  "ink-gray-9",
  "ink-gray-5",
  "outline-gray-2",
  "surface-accent-6",
  "ink-accent-link",
] as const;

test.afterEach(async ({ apiAs }) => {
  const agent = await apiAs("agent");
  await agent.call("helpdesk.api.theme.set_desk_theme", { theme: "Light" });
});

for (const mode of ["light", "dark"] as const) {
  test(`${mode} mode paints the generated tokens`, async ({ page }) => {
    await page.goto("/helpdesk");
    await page.evaluate(
      (m) => document.documentElement.setAttribute("data-theme", m),
      mode
    );
    const painted = await page.evaluate(
      (names) =>
        names.map((n) =>
          getComputedStyle(document.documentElement)
            .getPropertyValue(`--${n}`)
            .trim()
            .toLowerCase()
        ),
      [...SAMPLE]
    );
    expect(painted).toEqual(SAMPLE.map((n) => tokens[mode][n].toLowerCase()));
  });
}

test("the saved theme is applied before the app mounts", async ({
  page,
  apiAs,
}) => {
  const agent = await apiAs("agent");
  await agent.call("helpdesk.api.theme.set_desk_theme", { theme: "Dark" });
  await page.addInitScript(() => {
    document.addEventListener("DOMContentLoaded", () => {
      (window as any).__themeAtParse =
        document.documentElement.getAttribute("data-theme");
    });
  });
  await page.goto("/helpdesk");
  expect(await page.evaluate(() => (window as any).__themeAtParse)).toBe(
    "dark"
  );
});

test("toggling the theme from the command palette is saved on the user", async ({
  page,
  api,
  apiAs,
}) => {
  const agent = await apiAs("agent");
  await agent.call("helpdesk.api.theme.set_desk_theme", { theme: "Light" });
  await page.goto("/helpdesk");
  await page.keyboard.press("Control+k");
  const palette = page.getByRole("dialog", { name: "Command Palette" });
  await palette.getByRole("combobox").fill("Toggle theme");
  await palette.getByRole("option", { name: /Toggle theme/ }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await expect
    .poll(async () => (await api.get("User", emailOf("agent"))).desk_theme)
    .toBe("Dark");
});
