<template>
  <!-- Stands in for the framework's ActivityTimeline/TimeAgo.vue on the agent ticket page (see vite.config.js).
       Same prop and the same base classes as the original, so every row keeps its layout; the longer text
       truncates (its tooltip has the full date) instead of pushing the reply / more icons out of the row. -->
  <GmailDate
    :timestamp="timestamp"
    class="min-w-0 truncate leading-6 text-ink-gray-5"
    v-bind="$attrs"
  />
</template>

<script setup lang="ts">
import GmailDate from "@/components/GmailDate.vue";

defineOptions({ inheritAttrs: false });
defineProps<{ timestamp: string }>();
</script>
