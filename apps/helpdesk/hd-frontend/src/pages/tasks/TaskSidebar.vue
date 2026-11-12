<template>
  <aside
    class="w-full shrink-0 border-t border-outline-gray-1 lg:w-80 lg:overflow-y-auto lg:border-s lg:border-t-0"
    :aria-label="__('Task details')"
  >
    <div class="divide-y divide-outline-gray-1">
      <section class="p-4">
        <h3 class="mb-3 text-base-medium text-ink-gray-8">
          {{ __("Task details") }}
        </h3>
        <dl class="grid grid-cols-[6.5rem_1fr] items-center gap-x-3 gap-y-3 text-p-sm">
          <dt class="text-ink-gray-5">{{ __("Status") }}</dt>
          <dd>
            <Badge
              :theme="statusTheme[task.status]"
              :class="statusBadgeClass[task.status]"
              :label="__(task.status)"
            />
          </dd>

          <dt class="self-start text-ink-gray-5">{{ __("Assignee") }}</dt>
          <dd class="min-w-0">
            <div class="flex items-start justify-between gap-2">
              <div class="min-w-0 space-y-0.5">
                <template v-if="task.assignee_type === 'Freelancer'">
                  <div class="truncate text-ink-gray-8">
                    {{ freelancerName }}
                  </div>
                  <div class="text-p-xs text-ink-gray-5">
                    {{ __("Freelancer") }}
                  </div>
                </template>
                <template v-else-if="task.hrms_employee_name">
                  <div class="truncate text-ink-gray-8">
                    {{ task.hrms_employee_name }}
                  </div>
                  <div class="text-p-xs text-ink-gray-5">
                    {{
                      [task.hrms_department, task.hrms_designation]
                        .filter(Boolean)
                        .join(" · ") || __("Employee")
                    }}
                  </div>
                  <TaskUser v-if="task.assignee" :user="task.assignee" />
                  <div v-else class="text-p-xs text-ink-gray-5">
                    {{ __("(no linked Help Desk user)") }}
                  </div>
                </template>
                <TaskUser v-else :user="task.assignee" />
              </div>
              <Button
                v-if="task.permissions.write"
                size="sm"
                variant="subtle"
                :label="__('Change')"
                @click="showAssign = true"
              />
            </div>
          </dd>

          <dt class="text-ink-gray-5">{{ __("Reviewer") }}</dt>
          <dd><TaskUser :user="task.reviewer_details" /></dd>
          <dt class="text-ink-gray-5">{{ __("Priority") }}</dt>
          <dd>
            <Badge
              :theme="priorityBadge[task.priority].theme"
              :variant="priorityBadge[task.priority].variant"
              :class="priorityBadgeClass[task.priority]"
              :label="__(task.priority)"
            />
          </dd>
          <dt class="text-ink-gray-5">{{ __("Project") }}</dt>
          <dd class="text-ink-gray-8">
            {{ task.pbt_project_name || projectName || "—" }}
          </dd>
          <dt class="text-ink-gray-5">{{ __("Milestone") }}</dt>
          <dd class="text-ink-gray-8">{{ milestoneName || "—" }}</dd>
          <dt class="text-ink-gray-5">{{ __("Start date") }}</dt>
          <dd class="text-ink-gray-8">{{ formatDate(task.start_date) }}</dd>
          <dt class="text-ink-gray-5">{{ __("Due date") }}</dt>
          <dd :class="overdue ? 'text-ink-red-8' : 'text-ink-gray-8'">
            {{ formatDate(task.due_date) }}
          </dd>
          <dt class="text-ink-gray-5">{{ __("Created by") }}</dt>
          <dd><TaskUser :user="task.creator" /></dd>
          <dt class="text-ink-gray-5">{{ __("Created") }}</dt>
          <dd class="text-ink-gray-8">{{ formatDate(task.creation) }}</dd>
        </dl>
      </section>

      <section class="p-4">
        <TaskChecklist
          :task="task"
          @saved="(t) => emit('saved', t)"
          @attached="emit('reload')"
        />
      </section>
    </div>

    <TaskAssignDialog
      v-model="showAssign"
      :task="task"
      :freelancers="options.freelancers || []"
      @assigned="(patch) => emit('updated', patch)"
    />
  </aside>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { Badge, Button, createResource, dayjs } from "frappe-ui";
import { computed, ref } from "vue";
import TaskAssignDialog from "./TaskAssignDialog.vue";
import TaskChecklist from "./TaskChecklist.vue";
import TaskUser from "./TaskUser.vue";
import {
  isOverdue,
  priorityBadge,
  priorityBadgeClass,
  statusBadgeClass,
  statusTheme,
  type TaskDetail,
} from "./taskMeta";

const props = defineProps<{ task: TaskDetail }>();
const emit = defineEmits<{
  updated: [patch: Partial<TaskDetail>];
  saved: [task: TaskDetail];
  reload: [];
}>();

const showAssign = ref(false);

// Names for the milestone and freelancer ids; the task record only carries the ids.
const formOptions = createResource({
  url: "helpdesk.api.task.get_task_form_options",
  method: "GET",
  params: props.task.project ? { project: props.task.project } : {},
  auto: true,
});
type FormOptions = {
  milestones?: { name: string; milestone_name: string }[];
  freelancers?: { name: string; freelancer_name: string }[];
};
const options = computed<FormOptions>(() => formOptions.data || {});
const milestoneName = computed(
  () =>
    options.value.milestones?.find((m) => m.name === props.task.milestone)
      ?.milestone_name || props.task.milestone
);
const freelancerName = computed(
  () =>
    options.value.freelancers?.find((f) => f.name === props.task.freelancer)
      ?.freelancer_name || props.task.freelancer
);
const projectName = computed(() => props.task.project);

const overdue = computed(() => isOverdue(props.task));
const formatDate = (value?: string | null) =>
  value ? dayjs(value).format("D MMM YYYY") : "—";
</script>
