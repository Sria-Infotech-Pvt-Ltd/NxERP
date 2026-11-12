<template>
  <form
    @submit.prevent="submit"
    @keydown.ctrl.enter.capture.stop.prevent="submit"
    @keydown.meta.enter.capture.stop.prevent="submit"
  >
    <Editor
      v-model="draft"
      :extensions="extensions"
      :editable="!sending"
      :placeholder="__('Write a reply')"
    >
      <!-- Recipients, laid out like the Ticket reply -->
      <div class="mx-5 flex items-center gap-2 border-y py-2.5">
        <span class="text-p-xs text-ink-gray-4">{{ __("To") }}:</span>
        <EmailMultiSelect
          v-model="to"
          class="flex-1"
          scope="contact"
          variant="ghost"
          allow-custom-email
          copy-on-click
          :validate="validateEmailWithZod"
          :custom-email-label="__('Add to recipients')"
        />
        <div class="flex gap-1.5">
          <Button
            type="button"
            :label="__('Cc')"
            variant="ghost"
            :class="
              cc.length || showCc ? '!bg-surface-gray-4 hover:bg-surface-gray-3' : '!text-ink-gray-4'
            "
            @click="showCc = !showCc"
          />
          <Button
            type="button"
            :label="__('Bcc')"
            variant="ghost"
            :class="
              bcc.length || showBcc ? '!bg-surface-gray-4 hover:bg-surface-gray-3' : '!text-ink-gray-4'
            "
            @click="showBcc = !showBcc"
          />
        </div>
      </div>
      <div v-if="showCc || cc.length" class="mx-5 flex items-center gap-2 border-b py-2.5">
        <span class="text-xs text-ink-gray-4">{{ __("Cc:") }}</span>
        <EmailMultiSelect
          v-model="cc"
          class="flex-1"
          scope="contact"
          variant="ghost"
          allow-custom-email
          copy-on-click
          :validate="validateEmailWithZod"
          :custom-email-label="__('Add to recipients')"
        />
      </div>
      <div v-if="showBcc || bcc.length" class="mx-5 flex items-center gap-2 border-b py-2.5">
        <span class="text-xs text-ink-gray-4">{{ __("Bcc:") }}</span>
        <EmailMultiSelect
          v-model="bcc"
          class="flex-1"
          scope="contact"
          variant="ghost"
          allow-custom-email
          copy-on-click
          :validate="validateEmailWithZod"
          :custom-email-label="__('Add to recipients')"
        />
      </div>

      <div class="max-h-[40vh] min-h-[7rem] overflow-y-auto">
        <EditorContent class="prose-sm mx-5 max-w-none py-3" />
      </div>
      <div class="flex flex-col gap-2 border-t">
        <ErrorMessage v-if="error" class="px-5 pt-2" :message="error" />
        <div class="flex items-center justify-between gap-2 px-4 py-2.5">
          <div class="min-w-0 flex-1 overflow-x-auto">
            <!-- No attach, image or video: files cannot be linked to the email of a task yet. -->
            <EditorFixedMenu :items="toolbar" />
          </div>
          <div class="flex shrink-0 items-center gap-x-2">
            <Button
              type="button"
              :label="__('Discard')"
              :disabled="sending"
              @click="discard"
            />
            <Button
              type="submit"
              variant="solid"
              :label="sendLabel"
              :loading="sending"
              :disabled="sending || isContentEmpty(draft) || !to.length"
            />
          </div>
        </div>
      </div>
    </Editor>
  </form>
</template>

<script setup lang="ts">
import { buildEditorExtensions, ClearFormatting } from "@/components/editor/config";
import EmailMultiSelect from "@/components/EmailMultiSelect.vue";
import { useDevice } from "@/composables";
import { __ } from "@/translation";
import { isContentEmpty, validateEmailWithZod } from "@/utils";
import { useStorage } from "@vueuse/core";
import { Button, createResource, ErrorMessage, toast } from "frappe-ui";
import {
  Blockquote,
  Bold,
  BulletList,
  Editor,
  EditorContent,
  EditorFixedMenu,
  HeadingGroup,
  InlineCode,
  InsertLink,
  Italic,
  OrderedList,
  Separator,
  Strike,
} from "frappe-ui/editor";
import { computed, ref } from "vue";
import type { TaskDetail } from "./taskMeta";

const props = defineProps<{ task: TaskDetail }>();
const emit = defineEmits<{ updated: [task: TaskDetail] }>();

const { isMac } = useDevice();
const error = ref("");
// Kept per task in this browser, like the comment draft; cleared only after the server accepted it.
const draft = useStorage<string>(`taskReply:${props.task.name}`, "");

// The assignee and the reviewer, worked out by the server. Edited freely; Discard puts them back.
const to = ref<string[]>([...(props.task.reply_recipients || [])]);
const cc = ref<string[]>([]);
const bcc = ref<string[]>([]);
const showCc = ref(false);
const showBcc = ref(false);

const sendLabel = computed(() =>
  isMac ? __("Send (⌘ + ⏎)") : __("Send (Ctrl + ⏎)")
);

const extensions = buildEditorExtensions();
const toolbar = [
  HeadingGroup,
  Separator,
  Bold,
  Italic,
  Strike,
  Separator,
  BulletList,
  OrderedList,
  Blockquote,
  InlineCode,
  Separator,
  InsertLink,
  ClearFormatting,
];

const reply = createResource({
  url: "helpdesk.api.task.reply_via_email",
  onSuccess(result: TaskDetail) {
    draft.value = "";
    cc.value = [];
    bcc.value = [];
    showCc.value = showBcc.value = false;
    error.value = "";
    toast.success(__("Reply queued to send"));
    emit("updated", result);
  },
  // The text is still in the editor (cleared only on success), so it can be sent again.
  onError(e: any) {
    error.value =
      e?.messages?.[0] || e?.message || __("Could not send the reply");
  },
});
const sending = computed(() => reply.loading);

function submit() {
  // The keyboard shortcut reaches here without passing the disabled button.
  if (sending.value || isContentEmpty(draft.value) || !to.value.length) return;
  error.value = "";
  reply.submit({
    name: props.task.name,
    message: draft.value,
    to: to.value.join(", "),
    cc: cc.value.join(", "),
    bcc: bcc.value.join(", "),
  });
}

function discard() {
  draft.value = "";
  error.value = "";
  to.value = [...(props.task.reply_recipients || [])];
  cc.value = [];
  bcc.value = [];
  showCc.value = showBcc.value = false;
}
</script>
