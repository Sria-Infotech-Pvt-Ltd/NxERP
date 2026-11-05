<template>
  <Dialog
    v-model:open="open"
    :title="__('Add Task')"
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
            :placeholder="
              form.project
                ? __('Search employee by name or ID')
                : __('Select project first')
            "
            :disabled="!form.project"
            :loading="employees.loading"
            :empty-text="employeeEmptyText"
            :description="employeeHint"
          />
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
            :label="__('Add Task')"
            theme="gray"
            variant="solid"
            :loading="saving"
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
  call,
  Combobox,
  createListResource,
  createResource,
  Dialog,
  ErrorMessage,
  FormControl,
  TabButtons,
  toast,
} from "frappe-ui";
import { computed, reactive, ref, watch } from "vue";
import { STATUSES } from "./taskMeta";

const open = defineModel<boolean>({ default: false });
const emit = defineEmits<{ created: [name: string] }>();

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
  assignee_type: "Employee",
  employee: "", // HRMS employee id, not a Frappe user id
  freelancer: "",
  status: "Planned",
  blocked_reason: "",
  start_date: "",
  due_date: "",
});
const form = reactive(blank());
const errors = reactive<Record<string, string>>({});
const saving = ref(false);
// One id per form: the server returns the same task if a create is sent twice.
const newRequestId = () =>
  globalThis.crypto?.randomUUID?.() ??
  `${Date.now()}-${Math.random().toString(36).slice(2)}`;
let requestId = newRequestId();

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

const hrmsEmployees = computed(() => employees.data || []);
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
  if (employeesError.value) return __("Employees could not be loaded");
  if (!hrmsEmployees.value.length) return __("No employees available");
  return __("No employees match your search");
});
const selectedEmployee = computed(() =>
  hrmsEmployees.value.find((e) => e.employee_id === form.employee)
);
const employeeHint = computed(() => {
  if (!form.project || employees.loading || employeesError.value) return "";
  if (!hrmsEmployees.value.length) return __("No employees available");
  if (selectedEmployee.value && !selectedEmployee.value.user)
    return __(
      "Not linked to a Help Desk user: the task keeps this employee but is not assigned to a user"
    );
  return "";
});
const freelancerOptions = computed(() =>
  withBlank(
    "",
    (options.data?.freelancers || []).map((f) => ({
      label: f.freelancer_name,
      value: f.name,
    }))
  )
);

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

watch(open, (isOpen) => {
  if (!isOpen) return;
  projects.fetch();
  localProjects.fetch();
  employees.fetch();
  loadOptions();
});

watch(
  () => form.project,
  () => {
    form.milestone = "";
    form.employee = "";
    employeeQuery.value = "";
    loadOptions();
  }
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
  if (form.status === "Blocked" && !form.blocked_reason.trim())
    errors.blocked_reason = __("Blocked reason is required");
  if (form.start_date && form.due_date && form.due_date < form.start_date)
    errors.due_date = __("End date cannot be earlier than the start date");
  return !Object.keys(errors).length;
}

async function save() {
  if (saving.value || !validate()) return;
  const isEmployee = form.assignee_type === "Employee";
  // The server re-reads the project and employee from PBT / HRMS and links a user by email.
  saving.value = true;
  try {
    const doc = await call("helpdesk.api.task.create_task", {
      request_id: requestId,
      doc: {
        doctype: "HD Task",
        subject: form.subject.trim(),
        status: form.status,
        blocked_reason: form.status === "Blocked" ? form.blocked_reason : null,
        project: localProject.value || null,
        pbt_project_id: pbtProjectId.value || null,
        milestone: form.milestone || null,
        assignee_type: form.assignee_type,
        hrms_employee_id: isEmployee ? form.employee || null : null,
        freelancer: isEmployee ? null : form.freelancer || null,
        start_date: form.start_date || null,
        due_date: form.due_date || null,
      },
    });
    toast.success(__("Task {0} created", [doc.name]));
    requestId = newRequestId();
    open.value = false;
    emit("created", doc.name);
  } catch (e: any) {
    errors.form =
      e?.messages?.[0] || e?.message || __("Could not create the task");
  } finally {
    saving.value = false;
  }
}
</script>
