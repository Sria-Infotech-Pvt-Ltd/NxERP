<template>
  <div class="flex min-h-0 flex-1 flex-col">
    <LayoutHeader>
      <template #left-header>
        <Breadcrumbs :items="breadcrumbs" />
      </template>
    </LayoutHeader>
    <div class="mx-auto min-h-0 w-full max-w-3xl flex-1">
      <TaskDetail :task-id="taskId" @close="goBack" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { LayoutHeader } from "@/components";
import { __ } from "@/translation";
import { Breadcrumbs, usePageMeta } from "frappe-ui";
import { computed } from "vue";
import { useRouter } from "vue-router";
import TaskDetail from "./TaskDetail.vue";

const props = defineProps<{ taskId: string }>();
const router = useRouter();

const breadcrumbs = computed(() => [
  { label: __("Tasks"), route: { name: "Tasks" } },
  {
    label: props.taskId,
    route: { name: "Task", params: { taskId: props.taskId } },
  },
]);

function goBack() {
  router.push({ name: "Tasks" });
}

usePageMeta(() => ({ title: props.taskId }));
</script>
