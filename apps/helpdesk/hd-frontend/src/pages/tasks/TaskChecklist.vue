<template>
  <div class="space-y-5">
    <section>
      <div class="mb-2 flex items-center justify-between">
        <h3 class="text-base-medium text-ink-gray-8">{{ __("Progress") }}</h3>
        <span class="text-p-sm text-ink-gray-7">{{ task.progress }}%</span>
      </div>
      <div
        class="h-2 overflow-hidden rounded-full bg-surface-gray-3"
        role="progressbar"
        :aria-valuenow="task.progress"
        aria-valuemin="0"
        aria-valuemax="100"
      >
        <div
          class="h-full rounded-full bg-surface-accent-6 transition-all"
          :style="{ width: `${task.progress}%` }"
        />
      </div>
      <p class="mt-2 text-p-xs text-ink-gray-5">
        {{ __("{0} of {1} done", [doneCount, task.checklist.length]) }}
      </p>

      <ul class="mt-3 space-y-1.5">
        <li
          v-for="(item, index) in task.checklist"
          :key="index"
          class="flex items-center gap-2"
        >
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
        class="mt-3 flex gap-2"
        @submit.prevent="addItem"
      >
        <FormControl
          v-model="newItem"
          class="flex-1"
          :placeholder="__('Add an item')"
          :aria-label="__('Add an item')"
        />
        <Button
          type="submit"
          :label="__('Add')"
          variant="subtle"
          :disabled="!newItem.trim()"
        />
      </form>
    </section>

    <section>
      <div class="flex items-center justify-between">
        <h3 class="text-base-medium text-ink-gray-8">
          {{ __("Attachments") }}
        </h3>
        <FileUploader
          v-if="task.permissions.write"
          :upload-args="{
            doctype: 'HD Task',
            docname: task.name,
            private: true,
          }"
          @success="emit('attached')"
        >
          <template #default="{ openFileSelector, uploading }">
            <Button
              variant="subtle"
              size="sm"
              :loading="uploading"
              @click="openFileSelector()"
            >
              <template #prefix><LucidePaperclip class="size-4" /></template>
              {{ __("Attach") }}
            </Button>
          </template>
        </FileUploader>
      </div>
      <ul class="mt-2 space-y-1">
        <li v-for="file in task.attachments" :key="file.name">
          <a
            :href="file.file_url"
            target="_blank"
            rel="noopener"
            class="text-p-sm text-ink-accent-link hover:underline"
          >
            {{ file.file_name }}
          </a>
        </li>
        <li v-if="!task.attachments.length" class="text-p-sm text-ink-gray-5">
          {{ __("No attachments") }}
        </li>
      </ul>
    </section>
  </div>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import {
  Button,
  Checkbox,
  createResource,
  FileUploader,
  FormControl,
  toast,
} from "frappe-ui";
import { computed, ref } from "vue";
import LucidePaperclip from "~icons/lucide/paperclip";
import type { TaskDetail } from "./taskMeta";

const props = defineProps<{ task: TaskDetail }>();
const emit = defineEmits<{ saved: [task: TaskDetail]; attached: [] }>();

const newItem = ref("");
const doneCount = computed(() => props.task.checklist.filter((i) => i.done).length);

const checklistResource = createResource({
  url: "helpdesk.api.task.update_checklist",
  onSuccess: (result: TaskDetail) => emit("saved", result),
  onError(error: any) {
    toast.error(
      error?.messages?.[0] || error?.message || __("Something went wrong")
    );
  },
});

function saveChecklist(items: { item: string; done: 0 | 1 }[]) {
  // A double-fired click would otherwise send the same change twice.
  if (checklistResource.loading) return;
  checklistResource.submit({ name: props.task.name, checklist: items });
}
const current = () =>
  props.task.checklist.map((i) => ({ item: i.item, done: i.done }));
function toggleItem(index: number, checked: boolean) {
  const items = current();
  const item = items[index];
  if (!item) return;
  item.done = checked ? 1 : 0;
  saveChecklist(items);
}
function addItem() {
  const text = newItem.value.trim();
  if (!text) return;
  saveChecklist([...current(), { item: text, done: 0 }]);
  newItem.value = "";
}
</script>
