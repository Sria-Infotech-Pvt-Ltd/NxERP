<template>
  <div>
    <Combobox
      :model-value="current"
      :options="groups"
      :disabled="!canWrite"
      :loading="employees.loading"
      :empty-text="__('No matches')"
      variant="ghost"
      trigger="button"
      @update:model-value="pick"
      @update:open="onOpen"
    >
      <template #trigger>
        <button
          type="button"
          :disabled="!canWrite || assign.loading"
          class="group flex w-full min-w-0 items-center gap-2 rounded-4 border border-transparent px-2 py-1 text-start enabled:hover:bg-surface-gray-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-3 disabled:cursor-default"
        >
          <Avatar v-if="name" :label="name" :image="image" size="md" />
          <div class="min-w-0 flex-1">
            <div
              class="truncate text-base"
              :class="name ? 'text-ink-gray-8' : 'text-ink-gray-4'"
            >
              {{ name || __("Set assignee...") }}
            </div>
            <div v-if="name && hint" class="truncate text-p-xs text-ink-gray-5">
              {{ hint }}
            </div>
          </div>
          <LucideChevronDown
            v-if="canWrite"
            class="invisible size-4 shrink-0 text-ink-gray-5 group-hover:visible group-focus-visible:visible"
          />
        </button>
      </template>
    </Combobox>
    <!-- HRMS down: freelancers can still be chosen, and the reason is shown where the choice is made. -->
    <p v-if="hrmsError" class="mt-1 px-2 text-p-xs text-ink-red-6">
      {{ hrmsError }}
    </p>
    <p v-if="assignError" class="mt-1 px-2 text-p-xs text-ink-red-6">
      {{ assignError }}
    </p>
  </div>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { Avatar, Combobox, createResource, toast } from "frappe-ui";
import { computed, ref } from "vue";
import LucideChevronDown from "~icons/lucide/chevron-down";
import type { TaskDetail } from "./taskMeta";

const props = defineProps<{
  task: TaskDetail;
  freelancers: { name: string; freelancer_name: string }[];
}>();
// Reassigning can take the task out of the caller's reach, so the page re-reads it (as it did after the old dialog).
const emit = defineEmits<{ assigned: [patch: Partial<TaskDetail>] }>();

const canWrite = computed(() => props.task.permissions.write);
const assignError = ref("");

const employees = createResource({
  url: "helpdesk.api.task.get_hrms_employees",
  method: "GET",
  auto: false,
});
// HRMS is only asked when the list is opened, not on every page view.
function onOpen(open: boolean) {
  if (open && !employees.data && !employees.loading) employees.fetch();
}
const hrmsError = computed(() => {
  const e = employees.error as { messages?: string[]; message?: string } | null;
  return e ? e.messages?.[0] || e.message || __("HRMS is unavailable") : "";
});

type HrmsEmployee = { employee_id: string; employee_name: string };
const employeeOptions = computed(() => {
  const list: HrmsEmployee[] = employees.data || [];
  const names = list.map((e) => e.employee_name);
  return list
    .map((e) => ({
      // Two employees can share a name, so add the id when it repeats.
      label:
        names.filter((n) => n === e.employee_name).length > 1
          ? `${e.employee_name} (${e.employee_id})`
          : e.employee_name,
      value: `emp:${e.employee_id}`,
    }))
    .sort((a, b) => a.label.localeCompare(b.label));
});
const freelancerOptions = computed(() =>
  props.freelancers.map((f) => ({ label: f.freelancer_name, value: `fl:${f.name}` }))
);
const groups = computed(() =>
  [
    { group: __("Employee (HRMS)"), options: employeeOptions.value },
    { group: __("Freelancer"), options: freelancerOptions.value },
  ].filter((g) => g.options.length)
);

const current = computed(() => {
  if (props.task.assignee_type === "Freelancer" && props.task.freelancer)
    return `fl:${props.task.freelancer}`;
  if (props.task.hrms_employee_id) return `emp:${props.task.hrms_employee_id}`;
  return null;
});

const freelancerName = computed(
  () =>
    props.freelancers.find((f) => f.name === props.task.freelancer)?.freelancer_name ||
    props.task.freelancer
);
const name = computed(() =>
  props.task.assignee_type === "Freelancer"
    ? freelancerName.value || ""
    : props.task.hrms_employee_name || props.task.assignee?.full_name || ""
);
const image = computed(() =>
  props.task.assignee_type === "Freelancer" ? undefined : props.task.assignee?.user_image || undefined
);
const hint = computed(() =>
  props.task.assignee_type === "Freelancer"
    ? __("Freelancer")
    : [__("Employee"), props.task.hrms_department, props.task.hrms_designation]
        .filter(Boolean)
        .join(" · ")
);

const assign = createResource({
  url: "helpdesk.api.task.assign_task",
  onSuccess(result: Partial<TaskDetail>) {
    assignError.value = "";
    toast.success(__("Task assigned"));
    emit("assigned", result);
  },
  onError(e: any) {
    assignError.value = e?.messages?.[0] || e?.message || __("Could not assign the task");
  },
});

function pick(value: unknown) {
  const choice = value == null ? "" : String(value);
  if (!choice || choice === current.value || assign.loading) return;
  assignError.value = "";
  if (choice.startsWith("fl:")) {
    assign.submit({
      name: props.task.name,
      assignee_type: "Freelancer",
      hrms_employee_id: null,
      freelancer: choice.slice(3),
    });
  } else if (choice.startsWith("emp:")) {
    assign.submit({
      name: props.task.name,
      assignee_type: "Employee",
      hrms_employee_id: choice.slice(4),
      freelancer: null,
    });
  }
}
</script>
