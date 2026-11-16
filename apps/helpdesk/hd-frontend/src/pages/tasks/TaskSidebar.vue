<template>
  <aside
    class="flex w-full shrink-0 flex-col border-t border-outline-gray-1 lg:h-full lg:w-80 lg:border-s lg:border-t-0"
    :aria-label="__('Task details')"
  >
    <!-- Header and timing, pinned above the scrolling sections like the ticket's contact + SLA block. -->
    <div class="shrink-0 space-y-4 p-4">
      <div class="flex items-center gap-3">
        <Avatar
          :label="creatorName"
          v-bind="task.creator?.user_image ? { image: task.creator.user_image } : {}"
          size="3xl"
        />
        <div class="flex min-w-0 flex-1 flex-col gap-1.5">
          <Tooltip :text="__('Created by')">
            <p class="min-h-[1lh] truncate text-md font-medium text-ink-gray-7">
              {{ creatorName }}
            </p>
          </Tooltip>
          <div class="flex items-center gap-1 text-p-sm text-ink-gray-6">
            <p
              class="cursor-copy transition-colors hover:text-ink-gray-8"
              @click="copyToClipboard(task.name, __('Task #{0} copied', [task.name]))"
            >
              #{{ task.name }}
            </p>
            <span>· {{ __("created {0}", [formatDate(task.creation)]) }}</span>
          </div>
        </div>
      </div>

      <div class="space-y-0.5">
        <TaskTimingRow
          :label="__('Start date')"
          :value="task.start_date"
          :timing="startInfo"
          :can-edit="canWrite"
          @change="(v) => save({ start_date: v })"
        />
        <TaskTimingRow
          :label="__('Due date')"
          :value="task.due_date"
          :timing="dueInfo"
          :can-edit="canWrite"
          @change="(v) => save({ due_date: v })"
        />
      </div>
    </div>

    <div class="min-h-0 flex-1 overflow-y-auto border-t border-outline-gray-1">
      <div class="divide-y-[1px] divide-outline-gray-1">
        <Section :label="__('Overview')" v-model:opened="openedSections.overview">
          <div class="space-y-2.5 pb-3 pt-0.5">
            <TaskFieldRow :label="__('Status')">
              <TaskStatusField :task="task" @change="(r) => emit('status', r)" />
            </TaskFieldRow>

            <TaskFieldRow :label="__('Assignee')">
              <TaskAssigneeField
                :task="task"
                :freelancers="options.freelancers || []"
                @assigned="(patch) => emit('updated', patch)"
              />
            </TaskFieldRow>

            <TaskFieldRow :label="__('Reviewer')">
              <TaskPickField
                :model-value="task.reviewer || null"
                :options="reviewerOptions"
                :placeholder="__('Set reviewer...')"
                :clear-label="__('No reviewer')"
                :saved-label="task.reviewer_details?.full_name"
                :disabled="!canWrite"
                @change="(v) => save({ reviewer: v })"
              />
            </TaskFieldRow>

            <TaskFieldRow :label="__('Priority')">
              <TaskPriorityField
                :priority="task.priority"
                :can-edit="canWrite"
                @change="(p) => save({ priority: p })"
              />
            </TaskFieldRow>

            <TaskFieldRow :label="__('Project')">
              <TaskPickField
                :model-value="projectValue"
                :options="projectOptions"
                :placeholder="__('Set project...')"
                :clear-label="__('No project')"
                :saved-label="task.pbt_project_name || task.project"
                :loading="pbtProjects.loading || localProjects.loading"
                :disabled="!canWrite"
                @open="(o) => o && loadProjects()"
                @change="changeProject"
              />
              <p v-if="projectError" class="mt-1 px-2 text-p-xs text-ink-red-6">
                {{ projectError }}
              </p>
            </TaskFieldRow>

            <TaskFieldRow :label="__('Milestone')">
              <TaskPickField
                :model-value="task.milestone || null"
                :options="milestoneOptions"
                :placeholder="__('Set milestone...')"
                :clear-label="__('No milestone')"
                :saved-label="milestoneName"
                :disabled="!canWrite || !task.project"
                @change="(v) => save({ milestone: v })"
              />
              <p v-if="milestoneHint" class="mt-1 px-2 text-p-xs text-ink-gray-5">
                {{ milestoneHint }}
              </p>
            </TaskFieldRow>
          </div>
        </Section>

        <TaskSideChecklist
          v-model:opened="openedSections.checklist"
          :task="task"
          @saved="(t) => emit('saved', t)"
        />

        <TaskSideAttachments
          v-model:opened="openedSections.attachments"
          :task="task"
          @changed="emit('reload')"
        />
      </div>
    </div>
  </aside>
</template>

<script setup lang="ts">
import Section from "@/components/Section.vue";
import { __ } from "@/translation";
import { copyToClipboard } from "@/utils";
import { useStorage } from "@vueuse/core";
import {
  Avatar,
  createListResource,
  createResource,
  dayjs,
  toast,
  Tooltip,
} from "frappe-ui";
import { computed, ref, watch } from "vue";
import TaskAssigneeField from "./TaskAssigneeField.vue";
import TaskFieldRow from "./TaskFieldRow.vue";
import TaskPickField from "./TaskPickField.vue";
import TaskPriorityField from "./TaskPriorityField.vue";
import TaskSideAttachments from "./TaskSideAttachments.vue";
import TaskSideChecklist from "./TaskSideChecklist.vue";
import TaskStatusField from "./TaskStatusField.vue";
import TaskTimingRow from "./TaskTimingRow.vue";
import type { TaskDetail, TaskStatus } from "./taskMeta";
import { dueTiming, startTiming } from "./taskTiming";

const props = defineProps<{ task: TaskDetail }>();
const emit = defineEmits<{
  updated: [patch: Partial<TaskDetail>];
  saved: [task: TaskDetail];
  reload: [];
  // A status was picked; the page owns the reason dialog and the update_status call.
  status: [request: { to: TaskStatus; needsReason: boolean; label: string }];
}>();

const canWrite = computed(() => props.task.permissions.write);
const openedSections = useStorage("taskSidebarSections", {
  overview: true,
  checklist: true,
  attachments: true,
});

const formatDate = (value?: string | null) =>
  value ? dayjs(value).format("D MMM YYYY") : "—";
const creatorName = computed(
  () => props.task.creator?.full_name || props.task.owner || ""
);

// Day counts use the site's "today" from the server, not the browser's clock.
const startInfo = computed(() => startTiming(props.task.start_date, props.task.today));
const dueInfo = computed(() =>
  dueTiming(props.task.due_date, props.task.status, props.task.today)
);

// One save path for every sidebar field. update_task_fields runs HDTask.validate, so a wrong-project
// milestone, a late due date or a disabled reviewer is refused by the server, whatever this form offers.
const saveFields = createResource({
  url: "helpdesk.api.task.update_task_fields",
  onSuccess(result: TaskDetail & { access_lost?: boolean }) {
    // Handing the review away can end the caller's own access: re-read, which shows the no-access page.
    if (result?.access_lost) emit("updated", {});
    else emit("saved", result);
  },
  onError(error: any) {
    toast.error(error?.messages?.[0] || error?.message || __("Could not save the change"));
  },
});
function save(values: Record<string, string>) {
  if (!canWrite.value || saveFields.loading) return;
  saveFields.submit({ name: props.task.name, values });
}

// Reviewer, freelancers and the milestones of the task's local project.
const formOptions = createResource({
  url: "helpdesk.api.task.get_task_form_options",
  method: "GET",
  params: props.task.project ? { project: props.task.project } : {},
  auto: true,
});
watch(
  () => props.task.project,
  (project) => {
    formOptions.fetch(project ? { project } : {});
  }
);
type FormOptions = {
  milestones?: { name: string; milestone_name: string }[];
  freelancers?: { name: string; freelancer_name: string }[];
  employees?: { user: string; agent_name?: string | null }[];
};
const options = computed<FormOptions>(() => formOptions.data || {});

const reviewerOptions = computed(() =>
  (options.value.employees || []).map((a) => ({
    label: a.agent_name || a.user,
    value: a.user,
  }))
);

const milestoneOptions = computed(() =>
  (options.value.milestones || []).map((m) => ({
    label: m.milestone_name,
    value: m.name,
  }))
);
const milestoneName = computed(
  () =>
    options.value.milestones?.find((m) => m.name === props.task.milestone)
      ?.milestone_name || props.task.milestone
);
const milestoneHint = computed(() => {
  if (props.task.pbt_project_id)
    return __("Milestones are not available for PBT projects yet");
  if (!props.task.project) return __("Choose a project first");
  if (!formOptions.loading && !options.value.milestones?.length)
    return __("This project has no milestones yet");
  return "";
});

// Same two sources as the New task dialog: PBT through the server proxy, plus local projects.
const pbtProjects = createResource({
  url: "helpdesk.api.task.get_pbt_projects",
  method: "GET",
  auto: false,
});
const localProjects = createListResource({
  doctype: "HD Task Project",
  fields: ["name", "project_name"],
  pageLength: 999,
  auto: false,
});
const projectsRequested = ref(false);
// Only asked for when the list is opened, so a page view never calls PBT.
function loadProjects() {
  if (projectsRequested.value) return;
  projectsRequested.value = true;
  pbtProjects.fetch();
  localProjects.fetch();
}
const projectError = computed(() => {
  const e = pbtProjects.error as { messages?: string[]; message?: string } | null;
  return e ? e.messages?.[0] || e.message || __("PBT projects could not be loaded") : "";
});
const projectOptions = computed(() =>
  [
    {
      group: __("PBT projects"),
      options: ((pbtProjects.data || []) as { project_id: string; project_name: string }[]).map(
        (p) => ({ label: p.project_name, value: `pbt:${p.project_id}` })
      ),
    },
    {
      group: __("Local projects"),
      options: ((localProjects.data || []) as { name: string; project_name: string }[]).map(
        (p) => ({ label: p.project_name, value: `local:${p.name}` })
      ),
    },
  ].filter((g) => g.options.length)
);
const projectValue = computed(() => {
  if (props.task.pbt_project_id) return `pbt:${props.task.pbt_project_id}`;
  if (props.task.project) return `local:${props.task.project}`;
  return null;
});

// A project change always empties the milestone (milestones belong to one local project), in the same save,
// so the server never sees a milestone that does not fit its project.
function changeProject(value: string) {
  if (value.startsWith("pbt:"))
    save({ pbt_project_id: value.slice(4), project: "", milestone: "" });
  else if (value.startsWith("local:"))
    save({ project: value.slice(6), pbt_project_id: "", milestone: "" });
  else save({ project: "", pbt_project_id: "", milestone: "" });
}
</script>
