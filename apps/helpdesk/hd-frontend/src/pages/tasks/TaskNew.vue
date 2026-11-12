<template>
  <div class="flex min-h-0 flex-1 flex-col">
    <LayoutHeader>
      <template #left-header>
        <Breadcrumbs :items="breadcrumbs" />
      </template>
    </LayoutHeader>

    <div class="min-h-0 flex-1 overflow-y-auto">
      <form
        class="mx-auto flex w-full max-w-4xl flex-col gap-5 px-5 py-6"
        novalidate
        @submit.prevent="submit"
      >
        <!-- Read-only summary of what the dialog collected; Edit / Assign reopens it. -->
        <div
          class="flex items-start justify-between gap-3 rounded-lg border border-outline-gray-2 bg-surface-gray-1 px-4 py-3"
        >
          <dl class="flex flex-wrap gap-x-6 gap-y-1 text-p-sm text-ink-gray-6">
            <div v-if="draft.projectLabel" class="flex gap-1.5">
              <dt>{{ __("Project") }}:</dt>
              <dd class="text-ink-gray-8">{{ draft.projectLabel }}</dd>
            </div>
            <div v-if="draft.milestoneLabel" class="flex gap-1.5">
              <dt>{{ __("Milestone") }}:</dt>
              <dd class="text-ink-gray-8">{{ draft.milestoneLabel }}</dd>
            </div>
            <div class="flex gap-1.5">
              <dt>{{ __(draft.assignee_type) }}:</dt>
              <dd class="text-ink-gray-8">
                {{ isAssigned ? draft.assigneeLabel || __("Selected") : __("Not assigned") }}
              </dd>
            </div>
            <div class="flex gap-1.5">
              <dt>{{ __("Status") }}:</dt>
              <dd class="text-ink-gray-8">{{ __(draft.status) }}</dd>
            </div>
            <div v-if="draft.due_date" class="flex gap-1.5">
              <dt>{{ __("Due date") }}:</dt>
              <dd class="text-ink-gray-8">{{ formatDate(draft.due_date) }}</dd>
            </div>
          </dl>
          <Button
            type="button"
            variant="subtle"
            :label="isAssigned ? __('Edit') : __('Assign')"
            :disabled="submitting"
            @click="openDialog"
          />
        </div>

        <ErrorMessage v-if="error" :message="error" />

        <div class="flex flex-col gap-2">
          <span class="block text-sm text-ink-gray-6">
            {{ __("Subject") }}
            <span class="place-self-center text-ink-red-5"> * </span>
          </span>
          <TextInput
            v-model="draft.subject"
            variant="outline"
            :placeholder="__('A short description')"
            maxlength="140"
            :disabled="submitting"
            @update:model-value="subjectError = ''"
          />
          <ErrorMessage v-if="subjectError" :message="subjectError" />
        </div>

        <!-- The ticket composer. Uploads are hidden: they would attach to a task that does not exist yet. -->
        <TicketTextEditor
          v-model:attachments="attachments"
          v-model:content="draft.description"
          :placeholder="__('Describe the task')"
          expand
          hide-uploads
        >
          <template #bottom-right>
            <Button
              type="submit"
              :label="__('Submit')"
              theme="gray"
              variant="solid"
              :loading="submitting"
            />
          </template>
        </TicketTextEditor>
      </form>
    </div>

    <NewTaskDialog v-model="showDialog" />
  </div>
</template>

<script setup lang="ts">
import { LayoutHeader } from "@/components";
import { __ } from "@/translation";
import { isContentEmpty } from "@/utils";
import TicketTextEditor from "@/pages/ticket/TicketTextEditor.vue";
import {
  Breadcrumbs,
  Button,
  call,
  dayjs,
  ErrorMessage,
  TextInput,
  toast,
  usePageMeta,
} from "frappe-ui";
import { computed, ref } from "vue";
import { useRouter } from "vue-router";
import NewTaskDialog from "./NewTaskDialog.vue";
import { clearTaskDraft, newRequestId, taskDraft } from "./taskDraft";

const router = useRouter();

// Opened directly or reloaded: start an empty draft, so the page works and Assign has something to fill.
if (!taskDraft.value)
  taskDraft.value = {
    subject: "",
    project: "",
    milestone: "",
    assignee_type: "Employee",
    hrms_employee_id: "",
    freelancer: "",
    status: "Planned",
    blocked_reason: "",
    start_date: "",
    due_date: "",
    description: "",
    projectLabel: "",
    milestoneLabel: "",
    assigneeLabel: "",
    requestId: newRequestId(),
  };
const draft = computed(() => taskDraft.value!);

const isAssigned = computed(
  () => !!(draft.value.hrms_employee_id || draft.value.freelancer)
);
const attachments = ref<File[]>([]);
const showDialog = ref(false);
const submitting = ref(false);
const error = ref("");
const subjectError = ref("");

const breadcrumbs = computed(() => [
  { label: __("Tasks"), route: { name: "Tasks" } },
  { label: __("New task"), route: { name: "TaskNew" } },
]);
const formatDate = (value: string) => dayjs(value).format("D MMM YYYY");

function openDialog() {
  // The dialog fills itself from the draft, subject and text included, and saves back to it.
  taskDraft.reopen = true;
  showDialog.value = true;
}

async function submit() {
  const current = taskDraft.value;
  if (submitting.value || !current) return;
  if (!current.subject.trim()) {
    subjectError.value = __("Subject is required");
    return;
  }
  submitting.value = true;
  error.value = "";
  const [kind, id = ""] = current.project.split(/:(.*)/s);
  try {
    // The server re-reads the project from PBT and applies the default assignee.
    // Sent with the draft's request id, so a retry returns the task already created.
    const doc = (await call("helpdesk.api.task.create_task", {
      request_id: current.requestId,
      doc: {
        doctype: "HD Task",
        subject: current.subject.trim(),
        project: kind === "local" ? id : null,
        pbt_project_id: kind === "pbt" ? id : null,
        milestone: current.milestone || null,
        assignee_type: current.assignee_type,
        hrms_employee_id:
          current.assignee_type === "Employee"
            ? current.hrms_employee_id || null
            : null,
        freelancer:
          current.assignee_type === "Freelancer"
            ? current.freelancer || null
            : null,
        status: current.status,
        blocked_reason:
          current.status === "Blocked" ? current.blocked_reason : null,
        description: isContentEmpty(current.description)
          ? null
          : current.description,
        start_date: current.start_date || null,
        due_date: current.due_date || null,
      },
    })) as { name: string };
    toast.success(__("Task created"));
    clearTaskDraft();
    router.replace({ name: "Task", params: { taskId: doc.name } });
  } catch (e: any) {
    // The draft, including the text, stays so the user can retry.
    error.value =
      e?.messages?.[0] || e?.message || __("Could not create the task");
  } finally {
    submitting.value = false;
  }
}

usePageMeta(() => ({ title: __("New task") }));
</script>
