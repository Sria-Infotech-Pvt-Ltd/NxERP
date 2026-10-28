<template>
  <div
    class="flex size-8 cursor-pointer items-center justify-center rounded-full bg-surface-gray-2 hover:bg-surface-gray-3"
    :class="{ 'ring-2 ring-outline-accent-4': selected }"
  >
    <img v-if="logoValue" :src="logoValue" class="size-4.5" />
    <LucideMail v-else class="size-4.5 text-ink-gray-7" />
  </div>
  <p v-if="serviceName" class="text-center text-p-xs text-ink-gray-7">
    {{ displayName }}
  </p>
</template>

<script setup lang="ts">
import { computed } from "vue";
import LucideMail from "~icons/lucide/mail";

interface P {
  serviceName?: string;
  logo?: string;
  selected?: boolean;
}

const props = withDefaults(defineProps<P>(), {
  serviceName: "",
  selected: false,
  logo: "",
});

const logoValue = computed(() => props.logo);
// stored service ids stay as they are; only the label shown to people changes
const displayName = computed(() => (props.serviceName === "Frappe Mail" ? "NXERP Mail" : props.serviceName));
</script>

<style scoped></style>
