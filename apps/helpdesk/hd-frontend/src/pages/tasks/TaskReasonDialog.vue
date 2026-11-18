<template>
  <Dialog v-model:open="open" :title="title" size="sm" @after-leave="reset">
    <template #default>
      <div class="space-y-3">
        <FormControl
          v-model="reason"
          type="textarea"
          :label="label"
          :rows="3"
          :required="true"
        />
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
            :loading="loading"
            @click="submit"
          />
        </div>
      </div>
    </template>
  </Dialog>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { Button, Dialog, ErrorMessage, FormControl } from "frappe-ui";
import { ref } from "vue";

const open = defineModel<boolean>({ default: false });
defineProps<{ title: string; label: string; loading?: boolean }>();
const emit = defineEmits<{ confirm: [reason: string] }>();

const reason = ref("");
const error = ref("");

function reset() {
  reason.value = "";
  error.value = "";
}

function submit() {
  if (!reason.value.trim()) {
    error.value = __("A reason is required");
    return;
  }
  error.value = "";
  emit("confirm", reason.value.trim());
}
</script>
