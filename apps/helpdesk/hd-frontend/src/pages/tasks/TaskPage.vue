<template>
  <div class="flex min-h-0 flex-1 flex-col">
    <LayoutHeader>
      <template #left-header>
        <Breadcrumbs :items="breadcrumbs" class="-ms-0.5" />
      </template>
      <template v-if="data" #right-header>
        <Badge
          :theme="statusTheme[data.status]"
          :class="statusBadgeClass[data.status]"
          :label="__(data.status)"
        />
        <template v-if="data.permissions.write">
          <Button
            v-for="action in actions"
            :key="action.label + action.to"
            :label="action.label"
            v-bind="actionProps(action.to)"
            :loading="statusResource.loading && pending?.to === action.to"
            @click="runAction(action)"
          />
          <Button
            v-if="data.status !== 'Cancelled' && data.status !== 'Completed'"
            :label="__('Cancel task')"
            variant="ghost"
            @click="runAction({ label: __('Cancel task'), to: 'Cancelled' })"
          />
        </template>
      </template>
    </LayoutHeader>

    <div v-if="task.loading && !data" class="grid flex-1 place-items-center">
      <LoadingIndicator class="size-6 text-ink-gray-4" />
    </div>
    <div
      v-else-if="!data"
      class="grid flex-1 place-items-center px-4 py-20 text-center"
    >
      <div class="space-y-2">
        <div class="text-md-medium text-ink-gray-8">
          {{ errorTitle }}
        </div>
        <p class="text-p-base text-ink-gray-6">{{ errorText }}</p>
        <Button :route="{ name: 'Tasks' }" variant="subtle">
          <template #prefix><LucideArrowLeft class="size-4" /></template>
          {{ __("Back to Tasks") }}
        </Button>
      </div>
    </div>

    <div v-else class="flex min-h-0 flex-1 flex-col overflow-y-auto lg:flex-row lg:overflow-hidden">
      <div class="flex min-w-0 flex-1 flex-col lg:overflow-hidden">
        <div class="shrink-0 border-b border-outline-gray-1 px-5 py-3">
          <div class="flex flex-wrap items-center gap-2 text-p-xs text-ink-gray-5">
            <span>{{ data.name }}</span>
            <Badge
              :theme="priorityBadge[data.priority].theme"
              :variant="priorityBadge[data.priority].variant"
              :class="priorityBadgeClass[data.priority]"
              :label="__(data.priority)"
            />
          </div>
          <h1 class="mt-1 text-xl-semibold text-ink-gray-9 break-words">
            {{ data.subject }}
          </h1>
          <p
            v-if="data.status === 'Blocked' && data.blocked_reason"
            class="mt-2 text-p-sm text-ink-gray-7"
          >
            <span class="font-medium">{{ __("Blocked") }}:</span>
            {{ data.blocked_reason }}
          </p>
        </div>

        <Tabs
          :model-value="activeTab"
          class="flex min-h-0 flex-1 flex-col lg:overflow-hidden"
          @update:model-value="changeTabTo"
        >
          <div class="flex shrink-0 items-center border-b border-outline-gray-1 px-5">
            <TabList size="md" class="flex-1 !border-b-0 py-1.5">
              <TabTrigger
                v-for="tab in tabs"
                :key="tab.value"
                :value="tab.value"
                :label="tab.label"
                :icon-left="tab.iconLeft"
              />
            </TabList>
          </div>
          <TabPanel
            v-for="tab in tabs"
            :key="tab.value"
            :value="tab.value"
            class="min-h-0 flex-1 flex-col overflow-auto data-[state=active]:flex"
          >
            <TaskActivityTab
              v-if="tab.value === 'activity'"
              :task="data"
              @updated="onSaved"
            />
            <TaskEmailsTab v-else-if="tab.value === 'email'" :task="data" />
            <TaskCommentsTab
              v-else-if="tab.value === 'comment'"
              :task="data"
              @updated="onSaved"
            />
            <TaskAnalyticsTab v-else :task="data" />
          </TabPanel>
        </Tabs>
      </div>

      <TaskSidebar
        :key="data.name"
        :task="data"
        @updated="onAssigned"
        @saved="onSaved"
        @reload="task.reload()"
      />
    </div>

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
import { LayoutHeader } from "@/components";
import { ActivityIcon, CommentIcon, EmailIcon } from "@/components/icons";
import { useActiveTabManager } from "@/composables/useActiveTabManager";
import { useAuthStore } from "@/stores/auth";
import { __ } from "@/translation";
import {
  Badge,
  Breadcrumbs,
  Button,
  createResource,
  LoadingIndicator,
  TabList,
  TabPanel,
  Tabs,
  TabTrigger,
  toast,
  usePageMeta,
} from "frappe-ui";
import { computed, ref, watch } from "vue";
import LucideArrowLeft from "~icons/lucide/arrow-left";
import LucideChartNoAxesColumn from "~icons/lucide/chart-no-axes-column";
import TaskActivityTab from "./TaskActivityTab.vue";
import TaskAnalyticsTab from "./TaskAnalyticsTab.vue";
import TaskCommentsTab from "./TaskCommentsTab.vue";
import TaskEmailsTab from "./TaskEmailsTab.vue";
import TaskReasonDialog from "./TaskReasonDialog.vue";
import TaskSidebar from "./TaskSidebar.vue";
import {
  nextActions,
  priorityBadge,
  priorityBadgeClass,
  statusBadgeClass,
  statusTheme,
  type TaskDetail,
  type TaskStatus,
} from "./taskMeta";

const props = defineProps<{ taskId: string }>();
const authStore = useAuthStore();

const task = createResource({
  url: "helpdesk.api.task.get_task",
  method: "GET",
  params: { name: props.taskId },
  auto: true,
  // Any failed load (access revoked, task deleted) must not leave the last copy on screen.
  onError: () => task.setData(null),
});
watch(
  () => props.taskId,
  (name) => {
    task.setData(null);
    task.submit({ name });
  }
);

const data = computed<TaskDetail | null>(() => task.data || null);
type LoadError = { exc_type?: string; httpStatus?: number; messages?: string[] };
const loadError = computed(() => task.error as LoadError | null);
const noAccess = computed(
  () =>
    loadError.value?.exc_type === "PermissionError" ||
    loadError.value?.httpStatus === 403
);
const errorTitle = computed(() =>
  noAccess.value ? __("No access to this task") : __("Task not found")
);
const errorText = computed(() =>
  noAccess.value
    ? __("You no longer have permission to view this task.")
    : loadError.value?.messages?.[0] ||
      __("You don't have access to this task, or it no longer exists.")
);

// Same order as the Ticket page: Activity, Emails, Comments, Analytics.
const tabs = computed(() => [
  { value: "activity", label: __("Activity"), iconLeft: ActivityIcon },
  { value: "email", label: __("Emails"), iconLeft: EmailIcon },
  { value: "comment", label: __("Comments"), iconLeft: CommentIcon },
  {
    value: "analytics",
    label: __("Analytics"),
    iconLeft: LucideChartNoAxesColumn,
  },
]);
const { activeTab, changeTabTo } = useActiveTabManager(tabs);

const breadcrumbs = computed(() => [
  { label: __("Tasks"), route: { name: "Tasks" } },
  {
    label: data.value?.subject || props.taskId,
    route: { name: "Task", params: { taskId: props.taskId } },
  },
]);

// The server decides; this only hides buttons that would always be rejected.
const actions = computed(() => {
  if (!data.value) return [];
  const isAssignee = data.value.assigned_to === authStore.userId;
  return nextActions(data.value.status).filter(
    (a) => !(a.to === "Completed" && isAssignee)
  );
});

/** A full task as returned by the status, checklist and comment endpoints. */
function onSaved(result: TaskDetail) {
  task.setData(result);
}
/** After a reassignment, trust only a fresh read: the user may no longer be allowed to see this task.
 * The old copy is dropped first, so nothing stale shows if the read is refused. */
function onAssigned() {
  task.setData(null);
  task.reload();
}

const showReason = ref(false);
const pending = ref<{ to: TaskStatus } | null>(null);
const statusResource = createResource({
  url: "helpdesk.api.task.update_status",
  onSuccess(result: TaskDetail) {
    showReason.value = false;
    onSaved(result);
  },
  onError(error: any) {
    toast.error(
      error?.messages?.[0] || error?.message || __("Something went wrong")
    );
  },
});
// theme is only passed when set: the Button prop does not accept an explicit undefined.
function actionProps(to: TaskStatus) {
  return to === "Completed"
    ? { variant: "solid" as const, theme: "gray" as const }
    : { variant: "subtle" as const };
}
function runAction(action: {
  to: TaskStatus;
  needsReason?: boolean;
  label?: string;
}) {
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

usePageMeta(() => ({ title: data.value?.subject || props.taskId }));
</script>
