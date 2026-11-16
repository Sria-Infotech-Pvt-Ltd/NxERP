<template>
  <Dropdown v-if="canEdit" :options="items" align="start" class="w-full">
    <template #default>
      <button
        type="button"
        class="group flex w-full min-w-0 items-center gap-2 rounded-4 border border-transparent px-2 py-0.5 text-start text-base text-ink-gray-8 hover:bg-surface-gray-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-3"
      >
        <TicketPriority :priority="priority" />
        <LucideChevronDown
          class="invisible ms-auto size-4 shrink-0 text-ink-gray-5 group-hover:visible group-focus-visible:visible"
        />
      </button>
    </template>
  </Dropdown>
  <div v-else class="border border-transparent px-2 py-0.5 text-base text-ink-gray-8">
    <TicketPriority :priority="priority" />
  </div>
</template>

<script setup lang="ts">
import TicketPriority from "@/components/TicketPriority.vue";
import { __ } from "@/translation";
import { Dropdown } from "frappe-ui";
import { h } from "vue";
import LucideChevronDown from "~icons/lucide/chevron-down";
import { PRIORITIES, type TaskPriority } from "./taskMeta";

const props = defineProps<{ priority: TaskPriority; canEdit: boolean }>();
const emit = defineEmits<{ change: [priority: TaskPriority] }>();

// Bars icon per level, the same component the ticket's Priority row uses.
const items = PRIORITIES.map((p) => ({
  label: __(p),
  icon: () => h(TicketPriority, { priority: p, iconOnly: true }),
  onClick: () => p !== props.priority && emit("change", p),
}));
</script>
