<template>
  <Dropdown v-if="items.length" :options="items" align="start" class="w-full">
    <template #default>
      <button
        type="button"
        class="group flex w-full min-w-0 items-center gap-2 rounded-4 border border-transparent px-2 py-0.5 text-start text-base text-ink-gray-8 hover:bg-surface-gray-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-3"
      >
        <IndicatorIcon class="shrink-0" :class="statusDot[task.status]" />
        <span class="truncate">{{ __(task.status) }}</span>
        <LucideChevronDown
          class="invisible ms-auto size-4 shrink-0 text-ink-gray-5 group-hover:visible group-focus-visible:visible"
        />
      </button>
    </template>
  </Dropdown>
  <!-- No move is possible (closed task, or no write access): plain text, no chevron. -->
  <div v-else class="flex min-w-0 items-center gap-2 border border-transparent px-2 py-0.5">
    <IndicatorIcon class="shrink-0" :class="statusDot[task.status]" />
    <span class="truncate text-base text-ink-gray-8">{{ __(task.status) }}</span>
  </div>
</template>

<script setup lang="ts">
import IndicatorIcon from "@/components/icons/IndicatorIcon.vue";
import { __ } from "@/translation";
import { Dropdown } from "frappe-ui";
import { computed, h } from "vue";
import LucideChevronDown from "~icons/lucide/chevron-down";
import { statusDot, type TaskDetail, type TaskStatus } from "./taskMeta";

const props = defineProps<{ task: TaskDetail }>();
const emit = defineEmits<{
  change: [request: { to: TaskStatus; needsReason: boolean; label: string }];
}>();

// Blocking a task, or sending one back from review, needs a written reason (the page opens the dialog).
function needsReason(to: TaskStatus) {
  return (
    to === "Blocked" || (props.task.status === "In Review" && to === "In Progress")
  );
}

// The server already filtered these (HDTask.validate stays the real check); this only hides the rest.
const items = computed(() =>
  (props.task.allowed_statuses || []).map((to) => ({
    label: __(to),
    icon: () => h(IndicatorIcon, { class: statusDot[to] }),
    onClick: () => emit("change", { to, needsReason: needsReason(to), label: __(to) }),
  }))
);
</script>
