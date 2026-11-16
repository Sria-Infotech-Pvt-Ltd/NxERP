<template>
  <div class="mx-auto w-full max-w-5xl space-y-5 px-5 py-4">
    <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      <div
        v-for="metric in metrics"
        :key="metric.label"
        class="rounded-lg border border-outline-gray-2 bg-surface-white p-4"
      >
        <div class="text-p-sm text-ink-gray-5">{{ metric.label }}</div>
        <div
          class="mt-1 text-xl-semibold"
          :class="metric.alert ? 'text-ink-red-8' : 'text-ink-gray-9'"
        >
          {{ metric.value }}
        </div>
        <div v-if="metric.hint" class="mt-0.5 text-p-xs text-ink-gray-5">
          {{ metric.hint }}
        </div>
      </div>
    </div>

    <section>
      <h2 class="mb-3 text-base-medium text-ink-gray-8">
        {{ __("Status history") }}
      </h2>
      <ol
        class="space-y-2 rounded-lg border border-outline-gray-2 bg-surface-white p-4"
      >
        <li class="flex items-center justify-between gap-3 text-p-sm">
          <span class="text-ink-gray-8">{{ __("Created") }}</span>
          <span class="text-ink-gray-5">{{
            formatDateTime(task.creation)
          }}</span>
        </li>
        <li
          v-for="(change, index) in statusChanges"
          :key="index"
          class="flex items-center justify-between gap-3 text-p-sm"
        >
          <span class="text-ink-gray-8">
            {{ __(String(change.old)) }} → {{ __(String(change.new)) }}
          </span>
          <span class="text-ink-gray-5">{{
            formatDateTime(change.creation)
          }}</span>
        </li>
      </ol>
    </section>
  </div>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { dayjs } from "frappe-ui";
import { computed } from "vue";
import { isOverdue, type TaskDetail } from "./taskMeta";

const props = defineProps<{ task: TaskDetail }>();

// Everything here is read from this task's own record and history: no SLA and no ticket data.
const statusChanges = computed(() =>
  props.task.activity
    .flatMap((entry) =>
      entry.changes
        .filter((c) => c.field === "status")
        .map((c) => ({ ...c, creation: entry.creation }))
    )
    .reverse()
);

const days = (n: number) => __("{0} d", [n]);

type Metric = {
  label: string;
  value: string;
  hint?: string | undefined;
  alert?: boolean;
};

const metrics = computed<Metric[]>(() => {
  const t = props.task;
  const done = t.checklist.filter((i) => i.done).length;
  const end = t.completed_on ? dayjs(t.completed_on) : dayjs();
  const age = Math.max(0, end.diff(dayjs(t.creation), "day"));
  const list: Metric[] = [
    { label: __("Progress"), value: `${t.progress}%` },
    {
      label: __("Checklist"),
      value: t.checklist.length ? `${done} / ${t.checklist.length}` : "—",
      hint: t.checklist.length ? undefined : __("No checklist items"),
    },
    {
      label: t.completed_on ? __("Time to complete") : __("Open for"),
      value: days(age),
    },
  ];
  if (!t.due_date) {
    list.push({ label: __("Due"), value: "—", hint: __("No due date") });
  } else if (isOverdue(t)) {
    const late = dayjs().startOf("day").diff(dayjs(t.due_date), "day");
    list.push({
      label: __("Due"),
      value: days(late),
      hint: __("overdue"),
      alert: true,
    });
  } else if (t.completed_on || t.status === "Cancelled") {
    list.push({ label: __("Due"), value: "—", hint: __("Closed") });
  } else {
    const left = dayjs(t.due_date).diff(dayjs().startOf("day"), "day");
    list.push({ label: __("Due"), value: days(left), hint: __("remaining") });
  }
  list.push(
    { label: __("Status changes"), value: String(statusChanges.value.length) },
    {
      label: __("Reassignments"),
      value: String(
        t.activity.filter((e) =>
          e.changes.some((c) => c.field === "assigned_to")
        ).length
      ),
    },
    { label: __("Comments"), value: String(t.comments.length) },
    { label: __("Attachments"), value: String(t.attachments.length) }
  );
  return list;
});

const formatDateTime = (value: string) =>
  dayjs(value).format("D MMM YYYY, h:mm A");
</script>
