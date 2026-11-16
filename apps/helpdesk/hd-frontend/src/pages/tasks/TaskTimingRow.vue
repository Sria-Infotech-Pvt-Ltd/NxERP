<template>
  <!-- Same row shape as the ticket's First Response / Resolution rows. -->
  <div class="flex min-h-7 items-center gap-2 leading-5">
    <FieldLabel :label="label" />
    <!-- 9px = a field control's 8px padding + 1px border, so values line up with the rows below -->
    <div class="flex min-w-0 flex-1 items-center gap-1.5 ps-[9px]">
      <DatePicker
        v-if="canEdit"
        :model-value="value || ''"
        clearable
        @update:model-value="onPick"
      >
        <template #trigger="{ setOpen }">
          <button
            type="button"
            class="min-w-0 truncate rounded-4 text-start text-base hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-3"
            :class="timingToneClass[timing.tone]"
            :aria-label="__('Change {0}', [label])"
            @click="setOpen(true)"
          >
            {{ timing.text }}
          </button>
        </template>
      </DatePicker>
      <span v-else class="min-w-0 truncate text-base" :class="timingToneClass[timing.tone]">
        {{ timing.text }}
      </span>
      <Tooltip v-if="timing.exact" :text="timing.exact">
        <LucideInfo class="size-3.5 shrink-0 cursor-pointer text-ink-gray-5" />
      </Tooltip>
    </div>
  </div>
</template>

<script setup lang="ts">
import FieldLabel from "@/components/FieldLabel.vue";
import { __ } from "@/translation";
import { DatePicker, Tooltip } from "frappe-ui";
import LucideInfo from "~icons/lucide/info";
import { timingToneClass, type Timing } from "./taskTiming";

const props = defineProps<{
  label: string;
  value?: string | null;
  timing: Timing;
  canEdit: boolean;
}>();
const emit = defineEmits<{ change: [value: string] }>();

function onPick(value: unknown) {
  const next = value ? String(value).slice(0, 10) : "";
  if (next === (props.value || "")) return;
  emit("change", next);
}
</script>
