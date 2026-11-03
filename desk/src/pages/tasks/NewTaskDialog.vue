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
        <ErrorMessage v-if="milestonesError" :message="milestonesError" />
        <ErrorMessage v-if="resourcesError" :message="resourcesError" />
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
            :disabled="pbtProjectId ? pbtMilestones.loading : options.loading"
            :description="milestoneHint"
          />

          <div class="col-span-2 flex items-center justify-between gap-3">
            <span class="text-base text-ink-gray-5">{{ __("Assign to") }}</span>
            <TabButtons v-model="form.assignee_type" :buttons="assigneeTypes" />
          </div>
          <!-- A PBT project assigns only the people PBT allocated to it (or to the chosen milestone). -->
          <div v-if="pbtProjectId" class="col-span-2 space-y-1.5">
            <label class="block text-base text-ink-gray-5">
              {{
                form.assignee_type === "Employee"
                  ? __("Select Employee")
                  : __("Select Freelancer")
              }}
            </label>
            <EmployeeAutocomplete
              v-model="resourceChoice"
              class="w-full"
              :options="resourceOptions"
              :placeholder="
                pbtResources.loading
                  ? __('Loading project resources...')
                  : __('Search by name or code')
              "
              :disabled="pbtResources.loading"
            >
              <template #prefix>
                <LucideSearch class="me-2 size-4 shrink-0 text-ink-gray-5" />
              </template>
              <template #item-label="{ option }">
                <span class="min-w-0 flex-1 truncate text-ink-gray-8">
                  {{ option.label }}
                </span>
                <span
                  v-if="option.meta"
                  class="ms-3 max-w-[50%] shrink-0 truncate text-xs text-ink-gray-5"
                >
                  {{ option.meta }}
                </span>
              </template>
            </EmployeeAutocomplete>
            <ErrorMessage v-if="errors.resource" :message="errors.resource" />
            <p v-else-if="resourceHint" class="text-xs text-ink-gray-5">
              {{ resourceHint }}
            </p>
          </div>
          <template v-else-if="form.assignee_type === 'Employee'">
            <div class="col-span-2 space-y-1.5">
              <label class="block text-base text-ink-gray-5">
                {{ __("Select Employee") }}
              </label>
              <!-- Searchable by name or employee id: the HRMS list is too long for a plain select. -->
              <EmployeeAutocomplete
                v-model="employeeChoice"
                class="w-full"
                :options="employeeOptions"
                :placeholder="
                  employees.loading
                    ? __('Loading employees...')
                    : __('Search employee by name or ID')
                "
                :disabled="employees.loading"
              >
                <template #prefix>
                  <LucideSearch class="me-2 size-4 shrink-0 text-ink-gray-5" />
                </template>
                <template #item-label="{ option }">
                  <span class="min-w-0 flex-1 truncate text-ink-gray-8">
                    {{ option.label }}
                  </span>
                  <span
                    v-if="option.meta"
                    class="ms-3 max-w-[50%] shrink-0 truncate text-xs text-ink-gray-5"
                  >
                    {{ option.meta }}
                  </span>
                </template>
              </EmployeeAutocomplete>
              <p v-if="employeeHint" class="text-xs text-ink-gray-5">
                {{ employeeHint }}
              </p>
            </div>
          </template>
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
            :label="__('Start Date')"
            :required="true"
            placeholder="dd-mm-yyyy"
            :error="errors.start_date"
          />
          <FormControl
            v-model="form.due_date"
            type="date"
            :label="__('End Date')"
            :required="true"
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
  createListResource,
  createResource,
  Dialog,
  ErrorMessage,
  FormControl,
  TabButtons,
  toast,
} from "frappe-ui";
import { computed, reactive, ref, watch } from "vue";
import EmployeeAutocomplete from "@/components/frappe-ui/Autocomplete.vue";
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
// Milestones of the selected PBT project, read from PBT whenever the project changes.
const pbtMilestones = createResource({
  url: "helpdesk.api.task.get_pbt_milestones",
  method: "GET",
  auto: false,
});
// Employees and freelancers PBT allocated to the project, narrowed to the milestone once one is picked.
const pbtResources = createResource({
  url: "helpdesk.api.task.get_pbt_resources",
  method: "GET",
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
  milestone: "", // PBT milestone_id for a PBT project, HD Task Milestone name for a local one
  assignee_type: "Employee",
  resource: "", // PBT assignment_id, used instead of employee / freelancer for a PBT project
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
// A response for a project that is no longer selected is ignored.
const currentPbtMilestones = computed(() =>
  pbtMilestones.params?.project_id === pbtProjectId.value
    ? pbtMilestones.data || []
    : []
);
const milestoneOptions = computed(() =>
  withBlank(
    __("No milestone"),
    pbtProjectId.value
      ? currentPbtMilestones.value.map((m) => ({
          label: m.status_display
            ? `${m.milestone_name} (${m.status_display})`
            : m.milestone_name,
          value: m.milestone_id,
        }))
      : (options.data?.milestones || []).map((m) => ({
          label: m.milestone_name,
          value: m.name,
        }))
  )
);
const milestoneHint = computed(() => {
  if (pbtProjectId.value)
    return !pbtMilestones.loading &&
      !milestonesError.value &&
      !currentPbtMilestones.value.length
      ? __("This project has no milestones in PBT")
      : "";
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
      meta: [e.designation, e.department].filter(Boolean).join(" · "),
    }))
    .sort((a, b) => a.label.localeCompare(b.label));
});
// The autocomplete hands back the chosen option (null when cleared); the form keeps the HRMS id.
const employeeChoice = computed({
  get: () => form.employee,
  set: (option: { value: string } | null) => {
    form.employee = option?.value ?? "";
  },
});
const selectedEmployee = computed(() =>
  hrmsEmployees.value.find((e) => e.employee_id === form.employee)
);
const employeeHint = computed(() => {
  if (employees.loading || employeesError.value) return "";
  if (!hrmsEmployees.value.length) return __("No employees available");
  if (selectedEmployee.value && !selectedEmployee.value.user)
    return __(
      "Not linked to a Help Desk user: the task keeps this employee but is not assigned to a user"
    );
  return "";
});
// PBT resources of the chosen type. A response for an earlier project or milestone is ignored.
const pbtMilestoneId = computed(() => (pbtProjectId.value ? form.milestone : ""));
const currentPbtResources = computed(() => {
  const params = pbtResources.params;
  const isCurrent =
    params?.project_id === pbtProjectId.value &&
    (params?.milestone_id || "") === pbtMilestoneId.value;
  return isCurrent ? pbtResources.data || [] : [];
});
const resourceType = computed(() =>
  form.assignee_type === "Employee" ? "employee" : "freelancer"
);
const typedResources = computed(() =>
  currentPbtResources.value.filter((r) => r.resource_type === resourceType.value)
);
// One row per assignment: a repeated name gets its code, and its milestone shows in the meta.
const resourceOptions = computed(() => {
  const names = typedResources.value.map((r) => r.resource_name);
  return typedResources.value.map((r, i) => ({
    label:
      names.filter((n) => n === names[i]).length > 1 && r.resource_code
        ? `${names[i]} (${r.resource_code})`
        : names[i],
    value: r.assignment_id,
    meta: [r.role, r.milestone_name, r.resource_code]
      .filter(Boolean)
      .join(" · "),
  }));
});
const resourceChoice = computed({
  get: () => form.resource,
  set: (option: { value: string } | null) => {
    form.resource = option?.value ?? "";
  },
});
const selectedResource = computed(() =>
  typedResources.value.find((r) => r.assignment_id === form.resource)
);
const resourceHint = computed(() => {
  if (pbtResources.loading || resourcesError.value) return "";
  if (!typedResources.value.length)
    return form.assignee_type === "Employee"
      ? __("No employees are allocated to this project or milestone in PBT")
      : __("No freelancers are allocated to this project or milestone in PBT");
  const r = selectedResource.value;
  if (!r || r.resource_type !== "employee") return "";
  if (!r.resource_code)
    return __(
      "No AIRA employee ID in PBT: the task records this person but is not linked to HRMS or a Help Desk user"
    );
  const employee = hrmsEmployees.value.find(
    (e) => e.employee_id === r.resource_code
  );
  if (employee && !employee.user)
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
const milestonesError = computed(() => {
  const e = pbtProjectId.value ? errorText(pbtMilestones) : "";
  return e ? __("Could not load PBT milestones: {0}", [e]) : "";
});
const resourcesError = computed(() => {
  const e = pbtProjectId.value ? errorText(pbtResources) : "";
  return e ? __("Could not load PBT project resources: {0}", [e]) : "";
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
    loadOptions();
    if (pbtProjectId.value)
      pbtMilestones.fetch({ project_id: pbtProjectId.value });
    else pbtMilestones.reset();
  }
);
// The assignee list follows the PBT project and milestone, as PBT suggests: the whole project
// until a milestone is picked, then only that milestone's resources.
watch([pbtProjectId, pbtMilestoneId], ([projectId, milestoneId]) => {
  form.resource = "";
  if (!projectId) return pbtResources.reset();
  pbtResources.fetch({
    project_id: projectId,
    ...(milestoneId ? { milestone_id: milestoneId } : {}),
  });
});
watch(
  () => form.assignee_type,
  () => (form.resource = "")
);

function reset() {
  Object.assign(form, blank());
  Object.keys(errors).forEach((key) => delete errors[key]);
}

function validate() {
  Object.keys(errors).forEach((key) => delete errors[key]);
  if (!form.subject.trim()) errors.subject = __("Task title is required");
  if (form.assignee_type === "Freelancer") {
    if (pbtProjectId.value && !form.resource)
      errors.resource = __("Select a freelancer");
    else if (!pbtProjectId.value && !form.freelancer)
      errors.freelancer = __("Select a freelancer");
  }
  if (form.status === "Blocked" && !form.blocked_reason.trim())
    errors.blocked_reason = __("Blocked reason is required");
  if (!form.start_date) errors.start_date = __("Start date is required");
  if (!form.due_date) errors.due_date = __("End date is required");
  else if (form.start_date && form.due_date < form.start_date)
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
        milestone: localProject.value ? form.milestone || null : null,
        pbt_milestone_id: pbtProjectId.value ? form.milestone || null : null,
        assignee_type: form.assignee_type,
        pbt_assignment_id: pbtProjectId.value ? form.resource || null : null,
        hrms_employee_id:
          !pbtProjectId.value && isEmployee ? form.employee || null : null,
        freelancer:
          !pbtProjectId.value && !isEmployee ? form.freelancer || null : null,
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
