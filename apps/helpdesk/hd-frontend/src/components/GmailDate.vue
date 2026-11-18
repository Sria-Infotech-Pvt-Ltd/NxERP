<template>
  <Tooltip :text="full">
    <span v-bind="$attrs" class="whitespace-nowrap">{{ text }}</span>
  </Tooltip>
</template>

<script setup lang="ts">
// Gmail-style date for the agent ticket page and the task page: "Wed, Nov 11, 6:30 AM (1 day ago)", with the
// full date, time and zone on hover. The customer portal does not use this.
import { formatFullDateTime, formatGmailDate, useMinuteClock } from "@/utils/gmailDate";
import { Tooltip } from "frappe-ui";
import { computed } from "vue";

defineOptions({ inheritAttrs: false });
// A server timestamp (system time zone), the same prop name the framework's TimeAgo takes.
const props = defineProps<{ timestamp: string }>();

// Reading the clock inside the computed makes the "(N minutes ago)" part refresh every minute.
const clock = useMinuteClock();
const text = computed(() => formatGmailDate(props.timestamp, { now: clock.value }));
const full = computed(() => formatFullDateTime(props.timestamp));
</script>
