<template>
  <FrappeUIProvider>
    <router-view />
  </FrappeUIProvider>
  <Dialogs />
</template>

<script setup lang="ts">
import { Dialogs } from "@/components/dialogs";
import { useConfigStore } from "@/stores/config";
import { useAppTheme } from "@/theme/runtime/useAppTheme";
import { useFavicon } from "@vueuse/core";
import { FrappeUIProvider, setConfig, toast } from "frappe-ui";
import { storeToRefs } from "pinia";
import { h, onMounted } from "vue";
import Wifi from "~icons/lucide/wifi";
import WifiOff from "~icons/lucide/wifi-off";
import { __ } from "./translation";
import { isCustomerPortal } from "./utils";

const configStore = useConfigStore();
const { favicon } = storeToRefs(configStore);

useFavicon(favicon);

useAppTheme();

onMounted(() => {
  window.addEventListener("online", () => {
    toast(__("You are now online."), {
      icon: () => h(Wifi, { class: "text-ink-base" }),
    });
  });

  window.addEventListener("offline", () => {
    toast(__("You are now offline."), {
      icon: () => h(WifiOff, { class: "text-ink-base" }),
    });
  });
  !isCustomerPortal.value && setConfig("localTimezone", window.timezone?.user);
  setConfig("systemTimezone", window.timezone?.system || null);
});
</script>
