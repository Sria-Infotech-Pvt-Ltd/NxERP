<template>
  <Dialog
    v-model:open="open"
    :title="__('New task')"
    size="lg"
    @after-leave="reset"
  >
    <template #default>
      <!-- novalidate: field errors below are translated and consistent, unlike the browser bubble.
           Ctrl/Cmd+Enter saves from anywhere; plain Enter in the title must not submit. -->
      <form
        class="flex max-h-[calc(100vh-8rem)] flex-col gap-4"
        novalidate
        @submit.prevent="save"
        @keydown.ctrl.enter.prevent="save"
        @keydown.meta.enter.prevent="save"
      >
        <ErrorMessage
          v-if="loadError"
          :message="__('Could not load the form options: {0}', [loadError])"
        />
        <ErrorMessage v-if="projectsError" :message="projectsError" />
        <ErrorMessage v-if="employeesError" :message="employeesError" />
        <p v-if="projectLabel" class="-mt-3 text-p-sm text-ink-gray-5">
          {{ __("New task in {0}", [projectLabel]) }}
        </p>
        <!-- Only this body scrolls, and only on short screens; the footer stays put. -->
        <div
          class="-mx-1 grid min-h-0 flex-1 grid-cols-2 content-start gap-4 overflow-y-auto px-1 pb-1"
        >
          <FormControl
            v-model="form.subject"
            class="col-span-2"
            autofocus
            :label="__('Task Title')"
            :required="true"
            :placeholder="__('Enter task title')"
            :error="errors.subject"
            @keydown.enter.exact.prevent
          />
          <FormControl
            v-model="form.project"
            class="col-span-2"
            type="select"
            :label="__('Project')"
            :placeholder="__('Select project')"
            :options="projectOptions"
            :disabled="projects.loading"
            :description="
              hint(
                projects.loading || !!projectsError,
                projectOptions,
                __('No projects available')
              )
            "
          />
          <FormControl
            v-model="form.milestone"
            class="col-span-2"
            type="select"
            :label="__('Milestone')"
            :options="milestoneOptions"
            :disabled="options.loading || !!pbtProjectId"
            :description="milestoneHint"
          />

          <div class="col-span-2 flex items-center justify-between gap-3">
            <span class="text-base text-ink-gray-5">{{ __("Assign to") }}</span>
            <TabButtons v-model="form.assignee_type" :options="assigneeTypes" />
          </div>
          <!-- Searchable by name or employee id: the HRMS list is too long for a plain select.
               Filtered here, not by the combobox, because its own filter only matches the label. -->
          <Combobox
            v-if="form.assignee_type === 'Employee'"
            v-model="employeeChoice"
            v-model:query="employeeQuery"
            class="col-span-2"
            :label="__('Select Employee')"
            :options="filteredEmployeeOptions"
            :filterable="false"
            :placeholder="__('Search employee by name or ID')"
            :loading="employees.loading"
            :empty-text="employeeEmptyText"
            :description="employeeHint"
          />
          <p
            v-if="form.assignee_type === 'Employee' && errors.employee"
            class="col-span-2 -mt-3 text-p-sm text-ink-red-4"
          >
            {{ errors.employee }}
          </p>
          <FormControl
            v-else
            v-model="form.freelancer"
            class="col-span-2"
            type="select"
            :label="__('Select Freelancer')"
            :placeholder="__('Select freelancer')"
            :options="freelancerOptions"
            :disabled="options.loading"
            :error="errors.freelancer"
            :description="
              !options.loading && !options.data?.freelancers?.length
                ? __('No freelancers exist yet')
                : ''
            "
          />

          <FormControl
            v-model="form.status"
            class="col-span-2"
            type="select"
            :label="__('Status')"
            :options="STATUSES.map((s) => ({ label: __(s), value: s }))"
          />
          <FormControl
            v-if="form.status === 'Blocked'"
            v-model="form.blocked_reason"
            class="col-span-2"
            type="textarea"
            :label="__('Blocked reason')"
            :placeholder="__('Why is this task blocked?')"
            :error="errors.blocked_reason"
          />

          <FormControl
            v-model="form.start_date"
            type="date"
            :label="__('Start Date (Optional)')"
            placeholder="dd-mm-yyyy"
          />
          <FormControl
            v-model="form.due_date"
            type="date"
            :label="__('End Date (Optional)')"
            placeholder="dd-mm-yyyy"
            :error="errors.due_date"
          />
        </div>

        <ErrorMessage v-if="errors.form" :message="errors.form" />
        <div class="flex shrink-0 justify-end gap-2">
          <Button
            type="button"
            :label="__('Cancel')"
            variant="subtle"
            @click="open = false"
          />
          <Button
            type="submit"
            :label="__('Assigned')"
            theme="gray"
            variant="solid"
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
  createListResource,
  createResource,
  Dialog,
  ErrorMessage,
  FormControl,
  TabButtons,
} from "frappe-ui";
import { computed, reactive, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { STATUSES } from "./taskMeta";
import { clearTaskDraft, newRequestId, taskDraft } from "./taskDraft";

const open = defineModel<boolean>({ default: false });
const router = useRouter();
const route = useRoute();

// Projects come from PBT (server-side proxy). Local projects stay selectable because only they have milestones.
const projects = createResource({
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
const employees = createResource({
  url: "helpdesk.api.task.get_hrms_employees",
  method: "GET",
  auto: false,
});
// Milestones follow a local project and freelancers are local, so they are refetched on change.
const options = createResource({
  url: "helpdesk.api.task.get_task_form_options",
  method: "GET",
  auto: false,
});

const assigneeTypes = [
  { label: __("Employee"), value: "Employee" },
  { label: __("Freelancer"), value: "Freelancer" },
];

const blank = () => ({
  subject: "",
  project: "", // "pbt:<project_id>" or "local:<HD Task Project name>"
  milestone: "",
  assignee_type: "Employee" as "Employee" | "Freelancer",
  employee: "", // HRMS employee id, not a Frappe user id
  freelancer: "",
  status: "Planned",
  blocked_reason: "",
  start_date: "",
  due_date: "",
});
const form = reactive(blank());
const withBlank = (label: string, rows: { label: string; value: string }[]) => [
  { label, value: "" },
  ...rows,
];
const pbtProjectId = computed(() =>
  form.project.startsWith("pbt:") ? form.project.slice(4) : ""
);
const localProject = computed(() =>
  form.project.startsWith("local:") ? form.project.slice(6) : ""
);
const projectOptions = computed(() => [
  ...(projects.data || []).map((p) => ({
    label: p.project_name,
    value: `pbt:${p.project_id}`,
  })),
  ...(localProjects.data || []).map((p) => ({
    label: `${p.project_name} (${__("local")})`,
    value: `local:${p.name}`,
  })),
]);
const projectLabel = computed(
  () => projectOptions.value.find((p) => p.value === form.project)?.label
);
const milestoneOptions = computed(() =>
  withBlank(
    __("No milestone"),
    (options.data?.milestones || []).map((m) => ({
      label: m.milestone_name,
      value: m.name,
    }))
  )
);
const milestoneHint = computed(() => {
  if (pbtProjectId.value)
    return __("Milestones are not available for PBT projects yet");
  if (
    localProject.value &&
    !options.loading &&
    !options.data?.milestones?.length
  )
    return __("This project has no milestones yet");
  return "";
});

const hrmsEmployees = computed<
  { employee_id: string; employee_name: string; user?: string | null }[]
>(() => employees.data || []);
// Two employees can share a name, so add the id when a name repeats.
const employeeOptions = computed(() => {
  const names = hrmsEmployees.value.map((e) => e.employee_name);
  return hrmsEmployees.value
    .map((e, i) => ({
      label:
        names.filter((n) => n === names[i]).length > 1
          ? `${names[i]} (${e.employee_id})`
          : names[i],
      value: e.employee_id,
    }))
    .sort((a, b) => a.label.localeCompare(b.label));
});
const employeeQuery = ref("");
const filteredEmployeeOptions = computed(() => {
  const q = employeeQuery.value.trim().toLowerCase();
  if (!q) return employeeOptions.value;
  return employeeOptions.value.filter(
    (o) => o.label.toLowerCase().includes(q) || o.value.toLowerCase().includes(q)
  );
});
// The combobox reads null as "nothing selected"; the form keeps the HRMS id or "".
const employeeChoice = computed({
  get: () => form.employee || null,
  set: (value: string | null) => {
    form.employee = value ?? "";
  },
});
const employeeEmptyText = computed(() => {
  if (employees.error) return __("Employees could not be loaded");
  if (!hrmsEmployees.value.length) return __("No employees available");
  return __("No employees match your search");
});
const selectedEmployee = computed(() =>
  hrmsEmployees.value.find((e) => e.employee_id === form.employee)
);
const employeeHint = computed(() =>
  selectedEmployee.value && !selectedEmployee.value.user
    ? __(
        "Not linked to a Help Desk user: the task keeps this employee but is not assigned to a user"
      )
    : ""
);
const freelancerOptions = computed(() => [
  { label: "", value: "" },
  ...(options.data?.freelancers || []).map((f) => ({
    label: f.freelancer_name,
    value: f.name,
  })),
]);
const assigneeLabel = computed(() => {
  if (form.assignee_type === "Freelancer")
    return (
      (options.data?.freelancers || []).find((f) => f.name === form.freelancer)
        ?.freelancer_name || ""
    );
  return selectedEmployee.value?.employee_name || "";
});

const errorText = (r) => r.error?.messages?.[0] || r.error?.message || "";
const projectsError = computed(() => {
  const e = errorText(projects);
  return e ? __("Could not load PBT projects: {0}", [e]) : "";
});

const employeesError = computed(() => {
  const e = errorText(employees);
  return e ? __("Could not load HRMS employees: {0}", [e]) : "";
});

const loadError = computed(
  () => options.error?.messages?.[0] || options.error?.message || ""
);

function hint(loading: boolean, rows: unknown[], emptyText: string) {
  return !loading && !rows.length ? emptyText : "";
}

function loadOptions() {
  return options.fetch(localProject.value ? { project: localProject.value } : {});
}

const errors = reactive<Record<string, string>>({});

// An error goes as soon as its field is edited.
const clearError = (key: string) => () => delete errors[key];
watch(() => form.subject, clearError("subject"));
watch(() => form.employee, clearError("employee"));
watch(() => form.freelancer, clearError("freelancer"));
watch(() => form.blocked_reason, clearError("blocked_reason"));
watch(() => form.assignee_type, () => {
  delete errors.employee;
  delete errors.freelancer;
});
watch([() => form.start_date, () => form.due_date], clearError("due_date"));

// Set while a saved draft is put back, so picking its project does not clear its milestone.
let restoring = false;

watch(
  () => form.project,
  () => {
    if (restoring) restoring = false;
    else form.milestone = "";
    loadOptions();
  }
);

watch(
  open,
  (isOpen) => {
    if (!isOpen) return;
    projects.fetch();
    localProjects.fetch();
    employees.fetch();
    const draft = taskDraft.reopen ? taskDraft.value : null;
    if (draft) {
      // Back from the description page: put everything the user entered back.
      restoring = draft.project !== form.project;
      Object.assign(form, {
        subject: draft.subject,
        milestone: draft.milestone,
        assignee_type: draft.assignee_type,
        employee: draft.hrms_employee_id,
        freelancer: draft.freelancer,
        status: draft.status,
        blocked_reason: draft.blocked_reason,
        start_date: draft.start_date,
        due_date: draft.due_date,
      });
      form.project = draft.project;
      taskDraft.reopen = false;
    } else {
      clearTaskDraft();
    }
    loadOptions();
  },
  { immediate: true }
);

function reset() {
  Object.assign(form, blank());
  employeeQuery.value = "";
  Object.keys(errors).forEach((key) => delete errors[key]);
}

function validate() {
  Object.keys(errors).forEach((key) => delete errors[key]);
  if (!form.subject.trim()) errors.subject = __("Task title is required");
  if (form.assignee_type === "Freelancer" && !form.freelancer)
    errors.freelancer = __("Select a freelancer");
  if (form.assignee_type === "Employee" && !form.employee)
    errors.employee = __("Select an employee");
  if (form.status === "Blocked" && !form.blocked_reason.trim())
    errors.blocked_reason = __("Blocked reason is required");
  if (form.start_date && form.due_date && form.due_date < form.start_date)
    errors.due_date = __("End date cannot be earlier than the start date");
  return !Object.keys(errors).length;
}

// Nothing is created here: the task is created when the description page is submitted.
// The "Assigned" button saves the draft and goes (or stays) on that page.
function save() {
  if (!validate()) return;
  const previous = taskDraft.value;
  taskDraft.value = {
    subject: form.subject.trim(),
    project: form.project,
    milestone: form.milestone,
    assignee_type: form.assignee_type,
    hrms_employee_id: form.assignee_type === "Employee" ? form.employee : "",
    freelancer: form.assignee_type === "Freelancer" ? form.freelancer : "",
    status: form.status,
    blocked_reason: form.status === "Blocked" ? form.blocked_reason.trim() : "",
    assigneeLabel: assigneeLabel.value,
    start_date: form.start_date,
    due_date: form.due_date,
    description: previous?.description ?? "",
    projectLabel: projectLabel.value || "",
    milestoneLabel:
      milestoneOptions.value.find((m) => m.value === form.milestone)?.label ||
      "",
    requestId: previous?.requestId ?? newRequestId(),
  };
  taskDraft.reopen = false;
  open.value = false;
  // Opened from the description page (Edit / Assign): the draft is updated in place, no navigation.
  if (route.name !== "TaskNew") router.push({ name: "TaskNew" });
}
</script>
