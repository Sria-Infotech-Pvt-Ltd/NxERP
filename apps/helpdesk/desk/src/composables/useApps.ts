import { createResource } from "frappe-ui";
import { computed, h, markRaw, type Component, type ComputedRef } from "vue";
import AppsIcon from "@/components/icons/AppsIcon.vue";
import { isCustomerPortal } from "@/utils";

export interface App {
  name: string;
  logo: string;
  title: string;
  route: string;
}

interface AppsMenuOption {
  label: string;
  icon: Component;
  submenu: Array<{ label: string; icon: unknown; onClick: () => void }>;
}

/**
 * The apps this user may switch to. The list comes from `frappe.apps.get_apps`, which the NXERP platform
 * app overrides on the server to return only the apps the user is authorised for (nxerp.launcher).
 * The "Apps" menu is offered to multi-app users only, and always ends with a link back to the launcher.
 */
export function useApps() {
  const resource = createResource({
    url: "frappe.apps.get_apps",
    cache: "apps",
    // customers lack permission for get_apps; sidebar remounts on portal switch,
    // so this re-evaluates for agents
    auto: !isCustomerPortal.value,
    transform: (data: App[]) =>
      data.map((app) => ({
        name: app.name,
        logo: app.logo,
        title: app.title,
        route: app.route,
      })),
  });

  const apps = computed<App[]>(() => resource.data ?? []);

  const appsMenuOption: ComputedRef<AppsMenuOption> = computed(() => ({
    label: "Apps",
    icon: markRaw(AppsIcon),
    submenu: [
      ...apps.value
        .filter((app) => app.name !== "helpdesk")
        .map((app) => ({
          label: app.title,
          icon: h("img", { src: app.logo }),
          onClick: () => window.open(app.route, "_self"),
        })),
      {
        label: "All applications",
        icon: markRaw(AppsIcon),
        onClick: () => window.open("/nxerp/apps", "_self"),
      },
    ],
  }));

  // an app switcher only makes sense when there is something to switch to
  const appsMenuOptions = computed(() =>
    apps.value.length > 1 ? [appsMenuOption.value] : []
  );

  return { apps, appsMenuOption, appsMenuOptions };
}
