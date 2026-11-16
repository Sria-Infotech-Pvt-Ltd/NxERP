<template>
  <Combobox
    :model-value="modelValue"
    :options="allOptions"
    :disabled="disabled"
    :loading="loading"
    :empty-text="emptyText"
    variant="ghost"
    trigger="button"
    class="form-control !w-full !bg-surface-base"
    @update:model-value="onChange"
    @update:open="(o: boolean) => emit('open', o)"
  >
    <!-- The Combobox feeds one placeholder to both trigger and search box, so the empty state goes in
         the prefix slot instead (same trick as the ticket's fields). -->
    <template #prefix>
      <span class="truncate text-ink-gray-4">{{ placeholder }}</span>
    </template>
  </Combobox>
</template>

<script setup lang="ts">
import { Combobox } from "frappe-ui";
import { computed } from "vue";

type Option = { label: string; value: string };
type Group = { group: string; options: Option[] };
// A row that runs an action instead of picking a value (clearing the field).
type ActionRow = { type: "custom"; key: string; label: string; onClick: () => void };

const props = defineProps<{
  modelValue: string | null;
  // Plain options, or named groups of them.
  options: (Option | Group)[];
  placeholder: string;
  disabled?: boolean;
  loading?: boolean;
  emptyText?: string;
  // Label for the saved value when it is not (yet) among the options, such as a PBT project before its list loads.
  savedLabel?: string | null;
  // When set and the field has a value, a first row with this label empties the field. (The Combobox rejects
  // empty-string option values, so clearing is an action row, not an empty option.)
  clearLabel?: string;
}>();
const emit = defineEmits<{ change: [value: string]; open: [open: boolean] }>();

const flat = computed<Option[]>(() =>
  props.options.flatMap((o) => ("group" in o ? o.options : [o]))
);

// The trigger shows the label of the matching option, so an unlisted saved value needs one.
const allOptions = computed<(Option | Group | ActionRow)[]>(() => {
  const value = props.modelValue;
  const rows: (Option | Group | ActionRow)[] = [...props.options];
  if (value && !flat.value.some((o) => o.value === value))
    rows.unshift({ label: props.savedLabel || value, value });
  if (value && props.clearLabel)
    rows.unshift({
      type: "custom",
      key: "__clear",
      label: props.clearLabel,
      onClick: () => emit("change", ""),
    });
  return rows;
});

function onChange(value: unknown) {
  const next = value == null ? "" : String(value);
  if (next === (props.modelValue ?? "")) return;
  emit("change", next);
}
</script>

<style scoped>
/* Flat like the ticket's fields: no border or fill, the chevron appears on hover or focus.
   visibility, not display, so the row never reflows. */
:deep(button.form-control[data-slot="trigger"]) {
  border-color: transparent;
  background: var(--surface-base);
  color: var(--ink-gray-7);
  gap: 0;
}
:deep(button.form-control[data-slot="trigger"] .lucide-chevron-down) {
  visibility: hidden;
}
:deep(button.form-control[data-slot="trigger"]:hover .lucide-chevron-down),
:deep(button.form-control[data-slot="trigger"]:focus .lucide-chevron-down),
:deep(button.form-control[data-slot="trigger"][data-state="open"] .lucide-chevron-down) {
  visibility: visible;
}
</style>
