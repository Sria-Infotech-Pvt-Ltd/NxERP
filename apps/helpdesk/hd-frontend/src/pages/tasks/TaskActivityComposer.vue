<template>
  <div class="shrink-0 border-t border-outline-gray-1 bg-surface-white">
    <!-- Reply / Comment, laid out and styled like the Ticket page's composer bar. Click one to open it, again to collapse. -->
    <div class="flex items-center gap-1.5 px-5 py-2.5">
      <Tooltip
        :text="task.permissions.write ? '' : __('You can reply only to tasks you can edit')"
      >
        <span class="inline-flex">
          <Button
            variant="ghost"
            :label="__('Reply')"
            :disabled="!task.permissions.write"
            :class="mode === 'reply' ? '!bg-surface-gray-4 hover:!bg-surface-gray-3' : ''"
            :aria-pressed="mode === 'reply'"
            @click="toggle('reply')"
          >
            <template #prefix><EmailIcon class="h-4" /></template>
          </Button>
        </span>
      </Tooltip>
      <Button
        variant="ghost"
        :label="__('Comment')"
        :class="mode === 'comment' ? '!bg-surface-gray-4 hover:!bg-surface-gray-3' : ''"
        :aria-pressed="mode === 'comment'"
        @click="toggle('comment')"
      >
        <template #prefix><CommentIcon class="h-4" /></template>
      </Button>
    </div>

    <TaskReplyComposer
      v-if="mode === 'reply'"
      :key="task.name"
      :task="task"
      @updated="(t) => emit('updated', t)"
      @keydown.esc.capture.stop="mode = null"
    />

    <form
      v-show="mode === 'comment'"
      @submit.prevent="submit"
      @keydown.ctrl.enter.capture.stop.prevent="submit"
      @keydown.meta.enter.capture.stop.prevent="submit"
      @keydown.esc.capture.stop="mode = null"
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
import { computed, ref } from "vue";
import TaskReplyComposer from "./TaskReplyComposer.vue";
import type { TaskDetail } from "./taskMeta";

const props = defineProps<{ task: TaskDetail }>();
const emit = defineEmits<{ updated: [task: TaskDetail] }>();

const { isMac } = useDevice();
// Which composer is open; clicking the active toggle collapses it.
const mode = ref<"reply" | "comment" | null>("comment");
const toggle = (m: "reply" | "comment") => (mode.value = mode.value === m ? null : m);
const error = ref("");
// Kept per task in this browser, so switching tabs does not lose what was typed (the Ticket composer does the same).
const draft = useStorage<string>(`taskActivityComment:${props.task.name}`, "");

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

const commentResource = createResource({
  url: "helpdesk.api.task.add_comment",
  onSuccess(result: TaskDetail) {
    draft.value = "";
    error.value = "";
    toast.success(__("Comment added"));
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

function discard() {
  draft.value = "";
  error.value = "";
}
</script>
