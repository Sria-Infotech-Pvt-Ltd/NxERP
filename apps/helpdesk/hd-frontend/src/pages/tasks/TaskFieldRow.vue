<template>
  <!-- Same row as the ticket sidebar: a fixed-width muted label, the control fills the rest. -->
  <div class="flex items-center gap-2 leading-5">
    <FieldLabel :label="label" />
    <div class="-m-1 min-h-[28px] min-w-0 flex-1 items-center p-1 text-base">
      <slot />
    </div>
  </div>
</template>

<script setup lang="ts">
import FieldLabel from "@/components/FieldLabel.vue";

defineProps<{ label: string }>();
</script>
