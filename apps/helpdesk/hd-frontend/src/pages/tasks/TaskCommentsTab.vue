<template>
  <div class="flex min-h-0 flex-1 flex-col">
    <ul class="mx-auto w-full max-w-4xl flex-1 space-y-4 px-5 py-4">
      <li v-for="comment in task.comments" :key="comment.name">
        <div class="flex items-center gap-2 text-p-xs text-ink-gray-5">
          <TaskUser :user="comment.user" />
          <span :title="comment.creation">{{ timeAgo(comment.creation) }}</span>
        </div>
        <!-- Sanitised server-side in get_comments. -->
        <div
          class="prose-f mt-1 rounded-lg border border-outline-gray-2 bg-surface-white p-3 text-p-sm text-ink-gray-8"
          v-html="comment.content"
        />
      </li>
      <li v-if="!task.comments.length" class="text-p-sm text-ink-gray-5">
        {{ __("No comments yet") }}
      </li>
    </ul>

    <form
      class="sticky bottom-0 shrink-0 border-t border-outline-gray-1 bg-surface-white"
      @submit.prevent="post"
    >
      <div class="mx-auto w-full max-w-4xl space-y-2 px-5 py-3">
        <Editor
          v-model="newComment"
          :extensions="extensions"
          :placeholder="__('Write a comment, @ to mention')"
        >
          <EditorContent
            class="prose-sm max-h-48 min-h-[4rem] max-w-none overflow-y-auto rounded border border-outline-gray-2 bg-surface-white px-3 py-2"
          />
        </Editor>
        <ErrorMessage v-if="error" :message="error" />
        <div class="flex justify-end">
          <Button
            type="submit"
            :label="__('Comment')"
            variant="solid"
            theme="gray"
            :loading="commentResource.loading"
            :disabled="isContentEmpty(newComment)"
          />
        </div>
      </div>
    </form>
  </div>
</template>

<script setup lang="ts">
import { buildEditorExtensions } from "@/components/editor/config";
import { __ } from "@/translation";
import { isContentEmpty } from "@/utils";
import { Button, createResource, dayjs, ErrorMessage } from "frappe-ui";
import { Editor, EditorContent } from "frappe-ui/editor";
import { ref } from "vue";
import TaskUser from "./TaskUser.vue";
import type { TaskDetail } from "./taskMeta";

const props = defineProps<{ task: TaskDetail }>();
const emit = defineEmits<{ updated: [task: TaskDetail] }>();

const newComment = ref("");
const error = ref("");

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

const commentResource = createResource({
  url: "helpdesk.api.task.add_comment",
  onSuccess(result: TaskDetail) {
    newComment.value = "";
    error.value = "";
    emit("updated", result);
  },
  // The text stays in the editor so the comment can be sent again.
  onError(e: any) {
    error.value =
      e?.messages?.[0] || e?.message || __("Could not post the comment");
  },
});

function post() {
  if (commentResource.loading || isContentEmpty(newComment.value)) return;
  commentResource.submit({ name: props.task.name, content: newComment.value });
}

const timeAgo = (value: string) => dayjs(value).fromNow();
</script>
