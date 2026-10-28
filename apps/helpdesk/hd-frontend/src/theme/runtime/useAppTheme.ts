import { call, useColorScheme, type ColorScheme } from "frappe-ui";
import { watch } from "vue";
import { tokens } from "../generated/tokens";

const DESK_VALUE: Record<ColorScheme, string> = {
  light: "Light",
  dark: "Dark",
  system: "Automatic",
};

let metaSynced = false;

function isLoggedIn() {
  const user = document.cookie.match(/(?:^|;\s*)user_id=([^;]*)/)?.[1];
  return !!user && user !== "Guest";
}

// Keeps the choice on the user record so Frappe Desk and other devices agree.
function persist(scheme: ColorScheme) {
  if (!isLoggedIn()) return;
  call("helpdesk.api.theme.set_desk_theme", {
    theme: DESK_VALUE[scheme],
  }).catch(() => {});
}

function syncThemeColorMeta(resolved: "light" | "dark") {
  document
    .querySelector('meta[name="theme-color"]')
    ?.setAttribute("content", tokens[resolved]["surface-base"]);
}

export function useAppTheme() {
  const scheme = useColorScheme();
  if (!metaSynced) {
    metaSynced = true;
    watch(scheme.resolvedColorScheme, syncThemeColorMeta, { immediate: true });
  }

  function setColorScheme(next: ColorScheme) {
    scheme.setColorScheme(next);
    persist(next);
  }

  function toggleColorScheme() {
    scheme.toggleColorScheme();
    persist(scheme.colorScheme.value);
  }

  return {
    colorScheme: scheme.colorScheme,
    resolvedColorScheme: scheme.resolvedColorScheme,
    setColorScheme,
    toggleColorScheme,
  };
}
