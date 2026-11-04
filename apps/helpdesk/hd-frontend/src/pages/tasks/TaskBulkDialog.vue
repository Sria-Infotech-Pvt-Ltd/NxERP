<template>
  <Dialog
    v-model:open="open"
    :title="mode === 'assign' ? __('Assign tasks') : __('Change status')"
    size="sm"
    @after-leave="reset"
  >
    <template #default>
      <div class="space-y-3">
        <p class="text-p-sm text-ink-gray-6">
          {{ __("{0} tasks selected", [names.length]) }}
        </p>
        <FormControl
          v-if="mode === 'assign'"
          v-model="assignee"
          type="select"
          :label="__('Assign to')"
          :options="agentOptions"
          :required="true"
        />
        <template v-else>
          <FormControl
            v-model="status"
            type="select"
            :label="__('Status')"
            :options="statusOptions"
            :required="true"
          />
          <FormControl
            v-if="status === 'Blocked' || status === 'In Progress'"
            v-model="reason"
            type="textarea"
            :rows="3"
            :label="
              status === 'Blocked'
                ? __('Why are these tasks blocked?')
                : __('Comment (needed when returning from review)')
            "
            :required="status === 'Blocked'"
          />
        </template>
        <ErrorMessage v-if="error" :message="error" />
        <div class="flex justify-end gap-2">
          <Button
            :label="__('Cancel')"
            variant="subtle"
            @click="open = false"
          />
          <Button
            :label="__('Confirm')"
            theme="gray"
            variant="solid"
            :loading="assignResource.loading || statusResource.loading"
            @click="submit"
          />
        </div>
      </div>
    </template>
  </Dialog>
</template>

<script setup lang="ts">
import { useAgentStore } from "@/stores/agent";
import { __ } from "@/translation";
import {
  Button,
  createResource,
  Dialog,
  ErrorMessage,
  FormControl,
  toast,
} from "frappe-ui";
import { computed, ref } from "vue";
import { STATUSES } from "./taskMeta";

const props = defineProps<{ mode: "assign" | "status"; names: string[] }>();
const open = defineModel<boolean>({ default: false });
const emit = defineEmits<{ done: [] }>();

const agentStore = useAgentStore();
if (!agentStore.agents.data) agentStore.agents.fetch();

const assignee = ref("");
const status = ref("");
const reason = ref("");
const error = ref("");

const agentOptions = computed(() => [
  { label: "", value: "" },
  ...(agentStore.dropdown || []).map(({ label, value }) => ({ label, value })),
]);
const statusOptions = [
  { label: "", value: "" },
  ...STATUSES.map((s) => ({ label: __(s), value: s })),
];

function reset() {
  assignee.value = status.value = reason.value = error.value = "";
}

function report(result: {
  updated: string[];
  failed: { name: string; error: string }[];
}) {
  if (result.updated.length)
    toast.success(__("{0} tasks updated", [result.updated.length]));
  if (result.failed.length)
    toast.error(
      result.failed
        .map((f) => `${f.name}: ${f.error || __("Not permitted")}`)
        .join("\n")
    );
  open.value = false;
  emit("done");
}

const assignResource = createResource({
  url: "helpdesk.api.task.bulk_assign",
  onSuccess: report,
  onError: (e: any) =>
    (error.value = e?.messages?.[0] || __("Bulk assignment failed")),
});
const statusResource = createResource({
  url: "helpdesk.api.task.bulk_update_status",
  onSuccess: report,
  onError: (e: any) =>
    (error.value = e?.messages?.[0] || __("Bulk status change failed")),
});

function submit() {
  error.value = "";
  if (props.mode === "assign") {
    if (!assignee.value) {
      error.value = __("Select an agent");
      return;
    }
    assignResource.submit({ names: props.names, assigned_to: assignee.value });
    return;
  }
  if (!status.value) {
    error.value = __("Select a status");
    return;
  }
  if (status.value === "Blocked" && !reason.value.trim()) {
    error.value = __("A reason is required");
    return;
  }
  statusResource.submit({
    names: props.names,
    status: status.value,
    reason: reason.value.trim() || undefined,
  });
}
</script>
