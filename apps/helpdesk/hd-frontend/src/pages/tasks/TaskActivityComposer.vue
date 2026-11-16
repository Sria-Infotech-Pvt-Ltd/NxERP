<template>
  <div class="shrink-0 border-t border-outline-gray-1 bg-surface-white">
    <!-- Reply / Comment bar, laid out like the Ticket page's. Nothing is open until one is clicked; clicking the
         open one closes it, and Cancel (right end, only while open) closes it too. Neither loses unsent text. -->
    <div class="flex justify-between gap-3 px-6 py-4 md:px-5 md:py-2.5">
      <div class="flex items-center gap-1.5">
        <Tooltip
          :text="task.permissions.write ? '' : __('You can reply only to tasks you can edit')"
        >
          <span class="relative inline-flex">
            <Button
              variant="ghost"
              :label="__('Reply')"
              :disabled="!task.permissions.write"
              :class="mode === 'reply' ? '!bg-surface-gray-4 hover:!bg-surface-gray-3' : ''"
              :aria-pressed="mode === 'reply'"
              :aria-label="hasReplyDraft ? __('Reply (unsent draft)') : undefined"
              @click="toggle('reply')"
            >
              <template #prefix><EmailIcon class="h-4" /></template>
            </Button>
            <DraftDot v-if="hasReplyDraft" />
          </span>
        </Tooltip>
        <span class="relative inline-flex">
          <Button
            variant="ghost"
            :label="__('Comment')"
            :class="mode === 'comment' ? '!bg-surface-gray-4 hover:!bg-surface-gray-3' : ''"
            :aria-pressed="mode === 'comment'"
            :aria-label="hasCommentDraft ? __('Comment (unsent draft)') : undefined"
            @click="toggle('comment')"
          >
            <template #prefix><CommentIcon class="h-4" /></template>
          </Button>
          <DraftDot v-if="hasCommentDraft" />
        </span>
      </div>
      <Button v-if="mode" variant="ghost" :label="__('Cancel')" @click="close">
        <template #prefix><LucideX class="size-4" /></template>
      </Button>
    </div>

    <!-- Mounted the first time it is opened, then only shown or hidden, so the unsent text and recipients stay. -->
    <TaskReplyComposer
      v-if="mounted.reply"
      v-show="mode === 'reply'"
      :key="task.name"
      :task="task"
      @updated="onSent"
      @keydown.esc.capture.stop="close"
    />

    <form
      v-if="mounted.comment"
      v-show="mode === 'comment'"
      @submit.prevent="submit"
      @keydown.ctrl.enter.capture.stop.prevent="submit"
      @keydown.meta.enter.capture.stop.prevent="submit"
      @keydown.esc.capture.stop="close"
    >
      <Editor
        v-model="draft"
        :extensions="extensions"
        :editable="!commentResource.loading"
        :placeholder="__('Write a comment, @ to mention')"
      >
        <!-- Scroll here so selected nodes are not clipped; capped so the history keeps room. -->
        <div class="max-h-[40vh] overflow-y-auto border-t">
          <EditorContent class="prose-sm mx-5 min-h-[6rem] max-w-none py-3" />
        </div>
        <div class="flex flex-col gap-2 border-t">
          <ErrorMessage v-if="error" class="px-5 pt-2" :message="error" />
          <div class="flex items-center justify-between gap-2 px-4 py-2.5">
            <div class="min-w-0 flex-1 overflow-x-auto">
              <EditorFixedMenu :items="toolbar" />
            </div>
            <div class="flex shrink-0 items-center gap-x-2">
              <Button
                type="button"
                :label="__('Discard')"
                :disabled="commentResource.loading"
                @click="discard"
              />
              <Button
                type="submit"
                variant="solid"
                :label="submitLabel"
                :loading="commentResource.loading"
                :disabled="isContentEmpty(draft) || commentResource.loading"
              />
            </div>
          </div>
        </div>
      </Editor>
    </form>
  </div>
</template>

<script setup lang="ts">
import { buildEditorExtensions, ClearFormatting } from "@/components/editor/config";
import { CommentIcon, EmailIcon } from "@/components/icons";
import { useDevice } from "@/composables";
import { __ } from "@/translation";
import { isContentEmpty } from "@/utils";
import { useStorage } from "@vueuse/core";
import {
  Button,
  createResource,
  ErrorMessage,
  toast,
  Tooltip,
} from "frappe-ui";
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
import { computed, defineComponent, h, reactive, ref } from "vue";
import LucideX from "~icons/lucide/x";
import TaskReplyComposer from "./TaskReplyComposer.vue";
import type { TaskDetail } from "./taskMeta";

const props = defineProps<{ task: TaskDetail }>();
const emit = defineEmits<{ updated: [task: TaskDetail] }>();

// A dot on the button whose composer holds unsent text. Decorative (aria-hidden): the button's aria-label says it.
const DraftDot = defineComponent({
  name: "DraftDot",
  setup: () => () =>
    h("span", {
      class:
        "pointer-events-none absolute end-1 top-1 size-1.5 rounded-full bg-surface-accent-6",
      "aria-hidden": "true",
    }),
});

const { isMac } = useDevice();
// Which composer is open. Starts closed on every page load, even when a saved draft exists.
const mode = ref<"reply" | "comment" | null>(null);
// Each composer is created on first use and then kept, so switching never loses what was typed.
const mounted = reactive({ reply: false, comment: false });
function toggle(m: "reply" | "comment") {
  if (mode.value === m) return close();
  mounted[m] = true;
  mode.value = m;
}
// Cancel and Esc: hide the composer and keep the text (the per-task draft below).
function close() {
  mode.value = null;
}

const error = ref("");
// Kept per task in this browser, so switching tabs does not lose what was typed (the Ticket composer does the same).
const draft = useStorage<string>(`taskActivityComment:${props.task.name}`, "");
// The reply composer stores its text under this key; reading it here (same-page storage sync) drives the dot
// even before that composer has been opened.
const replyDraft = useStorage<string>(`taskReply:${props.task.name}`, "");
const hasCommentDraft = computed(() => !isContentEmpty(draft.value));
const hasReplyDraft = computed(() => !isContentEmpty(replyDraft.value));

const submitLabel = computed(() =>
  isMac ? __("Comment (⌘ + ⏎)") : __("Comment (Ctrl + ⏎)")
);

// Only users who can open this task are offered; the server re-checks on post.
const mentionable = createResource({
  url: "helpdesk.api.task.get_mentionable_users",
  method: "GET",
  params: { name: props.task.name },
  auto: true,
});
const extensions = buildEditorExtensions({
  mentions: () => mentionable.data ?? [],
});

// Comments only attach text: Task comments have no attachment API (files go to the task from the sidebar).
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

// The reply composer clears its own draft once the server accepted it; the bar then closes.
function onSent(result: TaskDetail) {
  close();
  emit("updated", result);
}

const commentResource = createResource({
  url: "helpdesk.api.task.add_comment",
  onSuccess(result: TaskDetail) {
    draft.value = "";
    error.value = "";
    toast.success(__("Comment added"));
    close();
    emit("updated", result);
  },
  // The text is still in the editor (it is cleared only on success), so the comment can be sent again.
  onError(e: any) {
    error.value =
      e?.messages?.[0] || e?.message || __("Could not post the comment");
  },
});

function submit() {
  // The keyboard shortcut reaches here without passing the disabled button.
  if (commentResource.loading || isContentEmpty(draft.value)) return;
  error.value = "";
  commentResource.submit({ name: props.task.name, content: draft.value });
}

// Discard clears the text (Cancel only hides the composer).
function discard() {
  draft.value = "";
  error.value = "";
}
</script>
