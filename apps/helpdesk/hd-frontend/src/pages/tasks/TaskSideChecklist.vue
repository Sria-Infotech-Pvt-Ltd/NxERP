<template>
  <Section :label="__('Checklist')" v-model:opened="opened">
    <template #actions>
      <span class="ms-auto text-p-sm text-ink-gray-6">{{ summary }}</span>
    </template>
    <div class="space-y-3 pb-3 pt-0.5">
      <!-- Progress is calculated by the server (HDTask.update_progress); this only draws it. -->
      <div
        class="h-1 overflow-hidden rounded-full bg-surface-gray-3"
        role="progressbar"
        :aria-label="__('Checklist progress')"
        :aria-valuenow="task.progress"
        aria-valuemin="0"
        aria-valuemax="100"
      >
        <div
          class="h-full rounded-full bg-surface-accent-6 transition-all"
          :style="{ width: `${task.progress}%` }"
        />
      </div>

      <ul v-if="task.checklist.length" class="space-y-1.5">
        <li v-for="(item, index) in task.checklist" :key="index">
          <Checkbox
            :model-value="!!item.done"
            :disabled="!task.permissions.write || checklistResource.loading"
            :label="item.item"
            @update:model-value="toggleItem(index, !!$event)"
          />
        </li>
      </ul>

      <form
        v-if="task.permissions.write"
        class="flex items-center gap-1.5"
        @submit.prevent="addItem"
      >
        <LucidePlus class="size-4 shrink-0 text-ink-gray-5" />
        <TextInput
          v-model="newItem"
          variant="ghost"
          class="flex-1"
          :placeholder="__('Add an item')"
          :aria-label="__('Add an item')"
        />
      </form>
    </div>
  </Section>
</template>

<script setup lang="ts">
import Section from "@/components/Section.vue";
import { __ } from "@/translation";
import { Checkbox, createResource, TextInput, toast } from "frappe-ui";
import { computed, ref } from "vue";
import LucidePlus from "~icons/lucide/plus";
import type { TaskDetail } from "./taskMeta";

const props = defineProps<{ task: TaskDetail }>();
const emit = defineEmits<{ saved: [task: TaskDetail] }>();
const opened = defineModel<boolean>("opened", { default: true });

const newItem = ref("");
const done = computed(() => props.task.checklist.filter((i) => i.done).length);
const summary = computed(() =>
  props.task.checklist.length
    ? __("{0} of {1} · {2}%", [done.value, props.task.checklist.length, props.task.progress])
    : __("No items")
);

const checklistResource = createResource({
  url: "helpdesk.api.task.update_checklist",
  onSuccess: (result: TaskDetail) => emit("saved", result),
  onError(error: any) {
    toast.error(error?.messages?.[0] || error?.message || __("Something went wrong"));
  },
});

function save(items: { item: string; done: 0 | 1 }[]) {
  // A double-fired click would otherwise send the same change twice.
  if (checklistResource.loading) return;
  checklistResource.submit({ name: props.task.name, checklist: items });
}
const current = () => props.task.checklist.map((i) => ({ item: i.item, done: i.done }));

function toggleItem(index: number, checked: boolean) {
  const items = current();
  const item = items[index];
  if (!item) return;
  item.done = checked ? 1 : 0;
  save(items);
}
function addItem() {
  const text = newItem.value.trim();
  if (!text) return;
  save([...current(), { item: text, done: 0 }]);
  newItem.value = "";
}
</script>
