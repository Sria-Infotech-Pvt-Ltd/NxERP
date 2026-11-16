<template>
  <Section :label="__('Attachments')" v-model:opened="opened">
    <template #actions>
      <FileUploader
        v-if="task.permissions.write"
        class="ms-auto"
        :upload-args="{ doctype: 'HD Task', docname: task.name, private: true }"
        @success="emit('changed')"
      >
        <template #default="{ openFileSelector, uploading }">
          <Tooltip :text="__('Attach a file')">
            <Button
              variant="ghost"
              size="sm"
              :loading="uploading"
              :aria-label="__('Attach a file')"
              @click.stop="openFileSelector()"
            >
              <template #icon><LucidePlus class="size-4" /></template>
            </Button>
          </Tooltip>
        </template>
      </FileUploader>
    </template>
    <div class="pb-3 pt-0.5">
      <ul v-if="task.attachments.length" class="flex flex-wrap gap-1.5">
        <li
          v-for="file in task.attachments"
          :key="file.name"
          class="flex max-w-full items-center gap-1 rounded-4 bg-surface-gray-2 py-1 ps-2 pe-1 text-p-sm"
        >
          <a
            :href="file.file_url"
            target="_blank"
            rel="noopener"
            class="truncate text-ink-accent-link hover:underline"
            >{{ file.file_name }}</a
          >
          <button
            v-if="task.permissions.write"
            type="button"
            class="grid size-5 shrink-0 place-items-center rounded-4 text-ink-gray-5 hover:bg-surface-gray-3 hover:text-ink-gray-8 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-3"
            :aria-label="__('Remove {0}', [file.file_name])"
            :disabled="removing === file.name"
            @click="remove(file)"
          >
            <LucideX class="size-3.5" />
          </button>
        </li>
      </ul>
      <p v-else class="text-p-sm text-ink-gray-5">{{ __("No attachments") }}</p>
    </div>
  </Section>
</template>

<script setup lang="ts">
import Section from "@/components/Section.vue";
import { __ } from "@/translation";
import { Button, createResource, FileUploader, toast, Tooltip } from "frappe-ui";
import { ref } from "vue";
import LucidePlus from "~icons/lucide/plus";
import LucideX from "~icons/lucide/x";
import type { TaskDetail } from "./taskMeta";

defineProps<{ task: TaskDetail }>();
const emit = defineEmits<{ changed: [] }>();
const opened = defineModel<boolean>("opened", { default: true });

const removing = ref("");
// Frappe's own File delete: it allows it only to someone who can write the attached task.
const removeFile = createResource({
  url: "frappe.client.delete",
  onSuccess() {
    removing.value = "";
    emit("changed");
  },
  onError(error: any) {
    removing.value = "";
    toast.error(error?.messages?.[0] || error?.message || __("Could not remove the file"));
  },
});

function remove(file: { name: string; file_name: string }) {
  if (removing.value || !window.confirm(__("Remove {0}?", [file.file_name]))) return;
  removing.value = file.name;
  removeFile.submit({ doctype: "File", name: file.name });
}
</script>
