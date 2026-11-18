<template>
  <Dialog v-model:open="open" :title="__('Assign task')" size="lg">
    <template #default>
      <form class="flex flex-col gap-4" novalidate @submit.prevent="save">
        <div class="flex items-center justify-between gap-3">
          <span class="text-base text-ink-gray-5">{{ __("Assign to") }}</span>
          <TabButtons v-model="assigneeType" :options="assigneeTypes" />
        </div>
        <!-- Searchable by name or employee id: the HRMS list is too long for a plain select.
             Filtered here, not by the combobox, because its own filter only matches the label. -->
        <Combobox
          v-if="assigneeType === 'Employee'"
          v-model="employeeChoice"
          v-model:query="employeeQuery"
          :label="__('Select Employee')"
          :options="filteredEmployeeOptions"
          :filterable="false"
          :placeholder="__('Search employee by name or ID')"
          :loading="employees.loading"
          :empty-text="employeeEmptyText"
          :description="employeeHint"
        />
        <FormControl
          v-else
          v-model="freelancer"
          type="select"
          :label="__('Select Freelancer')"
          :placeholder="__('Select freelancer')"
          :options="freelancerOptions"
          :description="freelancers.length ? '' : __('No freelancers exist yet')"
        />
        <ErrorMessage v-if="error" :message="error" />
        <div class="flex justify-end gap-2">
          <Button
            type="button"
            :label="__('Cancel')"
            variant="subtle"
            @click="open = false"
          />
          <Button
            type="submit"
            :label="__('Assign')"
            theme="gray"
            variant="solid"
            :loading="assign.loading"
          />
        </div>
      </form>
    </template>
  </Dialog>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import {
  Button,
  Combobox,
  createResource,
  Dialog,
  ErrorMessage,
  FormControl,
  TabButtons,
  toast,
} from "frappe-ui";
import { computed, ref, watch } from "vue";
import type { TaskDetail } from "./taskMeta";

const props = defineProps<{
  task: TaskDetail;
  freelancers: { name: string; freelancer_name: string }[];
}>();
const open = defineModel<boolean>({ default: false });
const emit = defineEmits<{ assigned: [patch: Partial<TaskDetail>] }>();

const assigneeTypes = [
  { label: __("Employee"), value: "Employee" },
  { label: __("Freelancer"), value: "Freelancer" },
];
const assigneeType = ref<"Employee" | "Freelancer">("Employee");
const employeeId = ref(""); // HRMS employee id, not a Frappe user id
const employeeQuery = ref("");
const freelancer = ref("");
const error = ref("");

const employees = createResource({
  url: "helpdesk.api.task.get_hrms_employees",
  method: "GET",
  auto: false,
});

watch(open, (isOpen) => {
  if (!isOpen) return;
  assigneeType.value = props.task.assignee_type || "Employee";
  employeeId.value = props.task.hrms_employee_id || "";
  freelancer.value = props.task.freelancer || "";
  employeeQuery.value = "";
  error.value = "";
  employees.fetch();
});

type HrmsEmployee = {
  employee_id: string;
  employee_name: string;
  user?: string | null;
};
const hrmsEmployees = computed<HrmsEmployee[]>(() => employees.data || []);
// Two employees can share a name, so add the id when a name repeats.
const employeeOptions = computed(() => {
  const names = hrmsEmployees.value.map((e) => e.employee_name);
  return hrmsEmployees.value
    .map((e) => ({
      label:
        names.filter((n) => n === e.employee_name).length > 1
          ? `${e.employee_name} (${e.employee_id})`
          : e.employee_name,
      value: e.employee_id,
    }))
    .sort((a, b) => a.label.localeCompare(b.label));
});
const filteredEmployeeOptions = computed(() => {
  const q = employeeQuery.value.trim().toLowerCase();
  if (!q) return employeeOptions.value;
  return employeeOptions.value.filter(
    (o) => o.label.toLowerCase().includes(q) || o.value.toLowerCase().includes(q)
  );
});
// The combobox reads null as "nothing selected"; the form keeps the HRMS id or "".
const employeeChoice = computed({
  get: () => employeeId.value || null,
  set: (value: string | null) => {
    employeeId.value = value ?? "";
  },
});
const employeeEmptyText = computed(() => {
  if (employees.error) return __("Employees could not be loaded");
  if (!hrmsEmployees.value.length) return __("No employees available");
  return __("No employees match your search");
});
const employeeHint = computed(() => {
  const selected = hrmsEmployees.value.find(
    (e) => e.employee_id === employeeId.value
  );
  return selected && !selected.user
    ? __(
        "Not linked to a Help Desk user: the task keeps this employee but is not assigned to a user"
      )
    : "";
});
const freelancerOptions = computed(() => [
  { label: "", value: "" },
  ...props.freelancers.map((f) => ({
    label: f.freelancer_name,
    value: f.name,
  })),
]);

const assign = createResource({
  url: "helpdesk.api.task.assign_task",
  onSuccess(result: Partial<TaskDetail>) {
    toast.success(__("Task assigned"));
    open.value = false;
    emit("assigned", result);
  },
  onError(e: any) {
    error.value = e?.messages?.[0] || e?.message || __("Could not assign the task");
  },
});

function save() {
  if (assign.loading) return;
  error.value = "";
  if (assigneeType.value === "Employee" && !employeeId.value)
    return void (error.value = __("Select an employee"));
  if (assigneeType.value === "Freelancer" && !freelancer.value)
    return void (error.value = __("Select a freelancer"));
  assign.submit({
    name: props.task.name,
    assignee_type: assigneeType.value,
    hrms_employee_id:
      assigneeType.value === "Employee" ? employeeId.value : null,
    freelancer: assigneeType.value === "Freelancer" ? freelancer.value : null,
  });
}
</script>
