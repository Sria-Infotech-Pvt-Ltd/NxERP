<template>
  <div class="flex h-full flex-col gap-3 overflow-y-auto p-3">
    <div v-if="task.loading && !task.data" class="flex justify-center py-10">
      <LoadingIndicator class="size-5" />
    </div>
    <ErrorMessage v-else-if="task.error" :message="errorText" />

    <template v-else-if="data">
      <!-- Card 1: header and workflow -->
      <section
        class="rounded-lg border border-outline-gray-2 bg-surface-white p-4"
      >
        <div class="flex items-start justify-between gap-2">
          <div class="min-w-0">
            <div class="text-p-xs text-ink-gray-5">{{ data.name }}</div>
            <h2 class="text-lg-medium text-ink-gray-9 break-words">
              {{ data.subject }}
            </h2>
          </div>
          <div class="flex shrink-0 items-center gap-2">
            <Badge
              :theme="statusTheme[data.status]"
              :class="statusBadgeClass[data.status]"
              :label="__(data.status)"
            />
            <Button
              variant="ghost"
              :class="closable ? '' : 'xl:hidden'"
              :aria-label="__('Close')"
              @click="$emit('close')"
            >
              <LucideX class="size-4" />
            </Button>
          </div>
        </div>

        <ol class="mt-4 grid grid-cols-4 gap-1" :aria-label="__('Workflow')">
          <li
            v-for="step in WORKFLOW_STEPS"
            :key="step"
            class="whitespace-nowrap rounded-full px-1 py-1 text-center text-xs"
            :class="
              step === data.status
                ? 'bg-surface-accent-6 text-ink-accent-on font-medium'
                : 'bg-surface-gray-2 text-ink-gray-6'
            "
            :aria-current="step === data.status ? 'step' : undefined"
          >
            {{ __(step) }}
          </li>
        </ol>
        <p
          v-if="data.status === 'Blocked' && data.blocked_reason"
          class="mt-3 text-p-sm text-ink-gray-7"
        >
          <span class="font-medium">{{ __("Blocked") }}:</span>
          {{ data.blocked_reason }}
        </p>

        <div
          v-if="data.permissions.write && actions.length"
          class="mt-4 flex flex-wrap gap-2"
        >
          <Button
            v-for="action in actions"
            :key="action.label + action.to"
            :label="action.label"
            :variant="action.to === 'Completed' ? 'solid' : 'subtle'"
            :theme="action.to === 'Completed' ? 'gray' : undefined"
            :loading="statusResource.loading && pending?.to === action.to"
            @click="runAction(action)"
          />
          <Button
            v-if="data.status !== 'Cancelled' && data.status !== 'Completed'"
            :label="__('Cancel task')"
            variant="ghost"
            @click="runAction({ label: __('Cancel task'), to: 'Cancelled' })"
          />
        </div>
      </section>

      <!-- Card 2: details -->
      <section
        class="rounded-lg border border-outline-gray-2 bg-surface-white p-4"
      >
        <h3 class="mb-3 text-base-medium text-ink-gray-8">
          {{ __("Details") }}
        </h3>
        <dl class="grid grid-cols-[7rem_1fr] gap-x-3 gap-y-2.5 text-p-sm">
          <dt class="text-ink-gray-5">{{ __("Assignee") }}</dt>
          <dd v-if="data.assignee || !data.hrms_employee_name">
            <TaskUser :user="data.assignee" />
          </dd>
          <dd v-else class="text-ink-gray-8">
            {{ data.hrms_employee_name }}
            <span class="text-ink-gray-5">
              {{ __("(no linked Help Desk user)") }}
            </span>
          </dd>
          <template v-if="data.hrms_department || data.hrms_designation">
            <dt class="text-ink-gray-5">{{ __("Department") }}</dt>
            <dd class="text-ink-gray-8">{{ data.hrms_department || "—" }}</dd>
            <dt class="text-ink-gray-5">{{ __("Designation") }}</dt>
            <dd class="text-ink-gray-8">{{ data.hrms_designation || "—" }}</dd>
          </template>
          <dt class="text-ink-gray-5">{{ __("Reviewer") }}</dt>
          <dd><TaskUser :user="data.reviewer_details" /></dd>
          <dt class="text-ink-gray-5">{{ __("Priority") }}</dt>
          <dd>
            <Badge
              :theme="priorityBadge[data.priority].theme"
              :variant="priorityBadge[data.priority].variant"
              :class="priorityBadgeClass[data.priority]"
              :label="__(data.priority)"
            />
          </dd>
          <dt class="text-ink-gray-5">{{ __("Start date") }}</dt>
          <dd class="text-ink-gray-8">{{ formatDate(data.start_date) }}</dd>
          <dt class="text-ink-gray-5">{{ __("Due date") }}</dt>
          <dd :class="overdue ? 'text-ink-red-8' : 'text-ink-gray-8'">
            {{ formatDate(data.due_date) }}
          </dd>
          <dt class="text-ink-gray-5">{{ __("Project") }}</dt>
          <dd class="text-ink-gray-8">
            {{ data.pbt_project_name || data.project || "—" }}
          </dd>
          <dt class="text-ink-gray-5">{{ __("Created by") }}</dt>
          <dd><TaskUser :user="data.creator" /></dd>
        </dl>
      </section>

      <!-- Card 3: progress and checklist -->
      <section
        class="rounded-lg border border-outline-gray-2 bg-surface-white p-4"
      >
        <div class="mb-2 flex items-center justify-between">
          <h3 class="text-base-medium text-ink-gray-8">{{ __("Progress") }}</h3>
          <span class="text-p-sm text-ink-gray-7">{{ data.progress }}%</span>
        </div>
        <div
          class="h-2 overflow-hidden rounded-full bg-surface-gray-3"
          role="progressbar"
          :aria-valuenow="data.progress"
          aria-valuemin="0"
          aria-valuemax="100"
        >
          <div
            class="h-full rounded-full bg-surface-accent-6 transition-all"
            :style="{ width: `${data.progress}%` }"
          />
        </div>
        <p class="mt-2 text-p-xs text-ink-gray-5">
          {{ __("{0} of {1} done", [doneCount, data.checklist.length]) }}
        </p>

        <ul class="mt-3 space-y-1.5">
          <li
            v-for="(item, index) in data.checklist"
            :key="index"
            class="flex items-center gap-2"
          >
            <Checkbox
              :model-value="!!item.done"
              :disabled="!data.permissions.write || checklistResource.loading"
              :label="item.item"
              @update:model-value="toggleItem(index, $event)"
            />
          </li>
        </ul>
        <form
          v-if="data.permissions.write"
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

      <!-- Card 4: description and attachments -->
      <section
        class="rounded-lg border border-outline-gray-2 bg-surface-white p-4"
      >
        <h3 class="mb-2 text-base-medium text-ink-gray-8">
          {{ __("Description") }}
        </h3>
        <!-- Sanitised server-side (sanitize_html) before it leaves get_task. -->
        <div
          v-if="data.description"
          class="prose-f max-w-none text-p-sm text-ink-gray-8"
          v-html="data.description"
        />
        <p v-else class="text-p-sm text-ink-gray-5">
          {{ __("No description") }}
        </p>

        <div class="mt-4 flex items-center justify-between">
          <h3 class="text-base-medium text-ink-gray-8">
            {{ __("Attachments") }}
          </h3>
          <FileUploader
            v-if="data.permissions.write"
            :upload-args="{
              doctype: 'HD Task',
              docname: data.name,
              private: true,
            }"
            @success="task.reload()"
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
          <li v-for="file in data.attachments" :key="file.name">
            <a
              :href="file.file_url"
              target="_blank"
              rel="noopener"
              class="text-p-sm text-ink-accent-link hover:underline"
            >
              {{ file.file_name }}
            </a>
          </li>
          <li v-if="!data.attachments.length" class="text-p-sm text-ink-gray-5">
            {{ __("No attachments") }}
          </li>
        </ul>
      </section>

      <!-- Card 5: comments and activity -->
      <section
        class="rounded-lg border border-outline-gray-2 bg-surface-white p-4"
      >
        <div class="mb-3 flex gap-1" role="tablist">
          <button
            v-for="tab in ['comments', 'activity']"
            :key="tab"
            role="tab"
            :aria-selected="activeTab === tab"
            class="rounded px-2.5 py-1 text-sm"
            :class="
              activeTab === tab
                ? 'bg-surface-gray-3 text-ink-gray-9 font-medium'
                : 'text-ink-gray-6 hover:bg-surface-gray-2'
            "
            @click="activeTab = tab"
          >
            {{ tab === "comments" ? __("Comments") : __("Activity") }}
          </button>
        </div>

        <template v-if="activeTab === 'comments'">
          <ul class="space-y-3">
            <li v-for="comment in data.comments" :key="comment.name">
              <div class="flex items-center gap-2 text-p-xs text-ink-gray-5">
                <TaskUser :user="comment.user" />
                <span>{{ timeAgo(comment.creation) }}</span>
              </div>
              <!-- Sanitised server-side in get_comments. -->
              <div
                class="prose-f mt-1 text-p-sm text-ink-gray-8"
                v-html="comment.content"
              />
            </li>
            <li v-if="!data.comments.length" class="text-p-sm text-ink-gray-5">
              {{ __("No comments yet") }}
            </li>
          </ul>
          <form class="mt-3 space-y-2" @submit.prevent="postComment">
            <Editor
              v-model="newComment"
              :extensions="extensions"
              :placeholder="__('Write a comment, @ to mention')"
            >
              <EditorContent
                class="prose-sm min-h-[4rem] max-h-48 max-w-none overflow-y-auto rounded border border-outline-gray-2 bg-surface-white px-3 py-2"
              />
            </Editor>
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
          </form>
        </template>

        <ul v-else class="space-y-3">
          <li
            v-for="(entry, index) in data.activity"
            :key="index"
            class="text-p-sm"
          >
            <div class="flex items-center gap-2 text-p-xs text-ink-gray-5">
              <TaskUser :user="entry.user" />
              <span>{{ timeAgo(entry.creation) }}</span>
            </div>
            <ul class="mt-1 text-ink-gray-7">
              <li v-for="change in entry.changes" :key="change.field">
                <template v-if="change.field === 'checklist'">
                  {{ __("Updated the checklist") }}
                </template>
                <template v-else>
                  {{
                    __("Changed {0} from {1} to {2}", [
                      change.field,
                      show(change.old),
                      show(change.new),
                    ])
                  }}
                </template>
              </li>
            </ul>
          </li>
          <li v-if="!data.activity.length" class="text-ink-gray-5">
            {{ __("No activity yet") }}
          </li>
        </ul>
      </section>
    </template>

    <TaskReasonDialog
      v-model="showReason"
      :title="
        pending?.to === 'Blocked'
          ? __('Mark as blocked')
          : __('Return to in progress')
      "
      :label="
        pending?.to === 'Blocked'
          ? __('Why is this blocked?')
          : __('What needs to change?')
      "
      :loading="statusResource.loading"
      @confirm="(reason) => changeStatus(pending!.to, reason)"
    />
  </div>
</template>

<script setup lang="ts">
import { buildEditorExtensions } from "@/components/editor/config";
import { useAuthStore } from "@/stores/auth";
import { isContentEmpty } from "@/utils";
import { __ } from "@/translation";
import {
  Badge,
  Button,
  Checkbox,
  createResource,
  dayjs,
  ErrorMessage,
  FileUploader,
  FormControl,
  LoadingIndicator,
  toast,
} from "frappe-ui";
import { Editor, EditorContent } from "frappe-ui/editor";
import { computed, ref, watch } from "vue";
import LucidePaperclip from "~icons/lucide/paperclip";
import LucideX from "~icons/lucide/x";
import TaskReasonDialog from "./TaskReasonDialog.vue";
import TaskUser from "./TaskUser.vue";
import {
  isOverdue,
  nextActions,
  priorityBadge,
  priorityBadgeClass,
  statusBadgeClass,
  statusTheme,
  WORKFLOW_STEPS,
  type TaskDetail,
  type TaskStatus,
} from "./taskMeta";

const props = defineProps<{ taskId: string; closable?: boolean }>();
const emit = defineEmits<{ close: []; changed: [] }>();

const authStore = useAuthStore();
const activeTab = ref("comments");
const newItem = ref("");
const newComment = ref("");
const showReason = ref(false);
const pending = ref<{ to: TaskStatus } | null>(null);

const task = createResource({
  url: "helpdesk.api.task.get_task",
  method: "GET",
  params: { name: props.taskId },
  auto: true,
});
watch(
  () => props.taskId,
  (name) => {
    task.submit({ name });
    mentionable.submit({ name });
  }
);

// Only users who can open this task are offered; the server re-checks on post.
const mentionable = createResource({
  url: "helpdesk.api.task.get_mentionable_users",
  method: "GET",
  params: { name: props.taskId },
  auto: true,
});
const extensions = buildEditorExtensions({
  mentions: () => mentionable.data ?? [],
});

const data = computed<TaskDetail | null>(() => task.data || null);
const errorText = computed(
  () => task.error?.messages?.[0] || __("Could not load this task")
);
const overdue = computed(() => !!data.value && isOverdue(data.value));
const doneCount = computed(
  () => data.value?.checklist.filter((i) => i.done).length ?? 0
);

// The server decides; this only hides buttons that would always be rejected.
const actions = computed(() => {
  if (!data.value) return [];
  const isAssignee = data.value.assigned_to === authStore.userId;
  return nextActions(data.value.status).filter(
    (a) => !(a.to === "Completed" && isAssignee)
  );
});

function onSaved(result: TaskDetail) {
  task.setData(result);
  emit("changed");
}
function onError(error: any) {
  toast.error(
    error?.messages?.[0] || error?.message || __("Something went wrong")
  );
}

const statusResource = createResource({
  url: "helpdesk.api.task.update_status",
  onSuccess(result: TaskDetail) {
    showReason.value = false;
    onSaved(result);
  },
  onError,
});
const checklistResource = createResource({
  url: "helpdesk.api.task.update_checklist",
  onSuccess: onSaved,
  onError,
});
const commentResource = createResource({
  url: "helpdesk.api.task.add_comment",
  onSuccess(result: TaskDetail) {
    newComment.value = "";
    onSaved(result);
  },
  onError,
});

function runAction(action: { to: TaskStatus; needsReason?: boolean }) {
  pending.value = action;
  if (action.needsReason) {
    showReason.value = true;
    return;
  }
  changeStatus(action.to);
}
function changeStatus(status: TaskStatus, reason?: string) {
  statusResource.submit({ name: props.taskId, status, reason });
}

function saveChecklist(items: { item: string; done: 0 | 1 }[]) {
  // A double-fired click would otherwise send the same change twice.
  if (checklistResource.loading) return;
  checklistResource.submit({ name: props.taskId, checklist: items });
}
function toggleItem(index: number, checked: boolean) {
  const items = data.value!.checklist.map((i) => ({
    item: i.item,
    done: i.done,
  }));
  items[index].done = checked ? 1 : 0;
  saveChecklist(items);
}
function addItem() {
  const text = newItem.value.trim();
  if (!text) return;
  const items = data.value!.checklist.map((i) => ({
    item: i.item,
    done: i.done,
  }));
  saveChecklist([...items, { item: text, done: 0 }]);
  newItem.value = "";
}
function postComment() {
  commentResource.submit({ name: props.taskId, content: newComment.value });
}

const formatDate = (value?: string | null) =>
  value ? dayjs(value).format("D MMM YYYY") : "—";
const timeAgo = (value: string) => dayjs(value).fromNow();
const show = (value: unknown) =>
  value === null || value === "" ? "—" : String(value);
</script>
