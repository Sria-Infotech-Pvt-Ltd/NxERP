<template>
  <div class="flex min-h-0 flex-1 flex-col">
    <!-- History scrolls on its own; the composer below stays put. -->
    <div ref="scroller" class="min-h-0 flex-1 overflow-y-auto">
      <ol class="mx-auto w-full max-w-4xl space-y-5 px-5 py-5">
        <li v-for="event in events" :key="event.key" class="flex gap-3">
          <div class="flex w-8 shrink-0 justify-center">
            <Avatar
              v-if="event.kind !== 'changes'"
              :label="event.user?.full_name || '?'"
              v-bind="
                event.user?.user_image ? { image: event.user.user_image } : {}
              "
              size="md"
            />
            <span
              v-else
              class="mt-2 size-2 rounded-full bg-surface-gray-5"
              aria-hidden="true"
            />
          </div>

          <div class="min-w-0 flex-1">
            <div class="flex flex-wrap items-center gap-x-2 text-p-sm">
              <span class="font-medium text-ink-gray-7">
                {{ event.user?.full_name || __("Unknown user") }}
              </span>
              <span class="text-ink-gray-6">
                <template v-if="event.kind === 'created'">
                  {{ __("created this task") }}
                </template>
                <template v-else-if="event.kind === 'description'">
                  {{ __("added a description") }}
                </template>
                <template v-else-if="event.kind === 'comment'">
                  {{ __("commented") }}
                </template>
                <template v-else-if="event.kind === 'email'">
                  {{ __("sent an email to {0}", [event.to || ""]) }}
                </template>
              </span>
              <GmailDate :timestamp="event.creation" class="text-ink-gray-5" />
            </div>

            <ul v-if="event.kind === 'changes'" class="mt-0.5 space-y-0.5 text-p-sm text-ink-gray-7">
              <li v-for="change in event.changes" :key="change.field">
                {{ describe(change) }}
              </li>
            </ul>
            <!-- Sanitised server-side (sanitize_html) before it leaves get_task / get_comments. -->
            <div
              v-else-if="['description', 'comment', 'email'].includes(event.kind)"
              class="prose-f mt-1.5 max-w-none rounded-lg border border-outline-gray-2 bg-surface-white p-3 text-p-sm text-ink-gray-8"
              v-html="event.content"
            />
          </div>
        </li>
      </ol>
    </div>

    <TaskActivityComposer :key="task.name" :task="task" @updated="(t) => emit('updated', t)" />
  </div>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { Avatar, dayjs } from "frappe-ui";
import { computed, nextTick, onMounted, ref, watch } from "vue";
import TaskActivityComposer from "./TaskActivityComposer.vue";
import GmailDate from "@/components/GmailDate.vue";
import type { TaskDetail, TaskUser as TaskUserData } from "./taskMeta";

const props = defineProps<{ task: TaskDetail }>();
const emit = defineEmits<{ updated: [task: TaskDetail] }>();

type Change = { field: string; old: unknown; new: unknown };
type Event = {
  key: string;
  kind: "created" | "description" | "changes" | "comment" | "email";
  creation: string;
  user?: TaskUserData | null | undefined;
  content?: string | undefined;
  to?: string | undefined;
  changes?: Change[] | undefined;
};

// Only real records of this task: its creation, its description, the Version log and its comments.
const events = computed<Event[]>(() => {
  const t = props.task;
  const list: Event[] = [
    { key: "created", kind: "created", creation: t.creation, user: t.creator },
  ];
  if (t.description) {
    // Shown as the creator's first message, like the description of a Ticket. It is the current text.
    list.push({
      key: "description",
      kind: "description",
      creation: t.creation,
      user: t.creator,
      content: t.description,
    });
  }
  t.activity.forEach((a, i) =>
    list.push({
      key: `change:${i}`,
      kind: "changes",
      creation: a.creation,
      user: a.user,
      changes: a.changes,
    })
  );
  t.comments.forEach((c) =>
    list.push({
      key: `comment:${c.name}`,
      kind: "comment",
      creation: c.creation,
      user: c.user,
      content: c.content,
    })
  );
  t.emails.forEach((e) =>
    list.push({
      key: `email:${e.name}`,
      kind: "email",
      creation: e.creation,
      user: e.user,
      content: e.content,
      to: e.recipients,
    })
  );
  // Stable sort: the description stays right after the creation row, which has the same time.
  return list.sort(
    (a, b) => dayjs(a.creation).valueOf() - dayjs(b.creation).valueOf()
  );
});

const LABELS: Record<string, string> = {
  status: __("status"),
  priority: __("priority"),
  assigned_to: __("assignee"),
  reviewer: __("reviewer"),
  project: __("project"),
  milestone: __("milestone"),
  start_date: __("start date"),
  due_date: __("due date"),
  progress: __("progress"),
  assignee_type: __("assignee type"),
  freelancer: __("freelancer"),
  hrms_employee_name: __("employee"),
  subject: __("title"),
};
const show = (value: unknown) =>
  value === null || value === undefined || value === "" ? "—" : String(value);

function describe(change: Change) {
  if (change.field === "checklist") return __("Updated the checklist");
  // The old and new text are whole HTML documents; the current one is shown above.
  if (change.field === "description") return __("Updated the description");
  if (change.field === "assigned_to" || change.field === "hrms_employee_name")
    return change.old
      ? __("Changed {0} from {1} to {2}", [
          LABELS[change.field] || change.field,
          show(change.old),
          show(change.new),
        ])
      : __("Assigned to {0}", [show(change.new)]);
  return __("Changed {0} from {1} to {2}", [
    LABELS[change.field] || change.field,
    show(change.old),
    show(change.new),
  ]);
}


// Newest at the bottom, next to the composer: open and update scrolled to the end.
const scroller = ref<HTMLElement | null>(null);
const toEnd = () =>
  nextTick(() => {
    if (scroller.value) scroller.value.scrollTop = scroller.value.scrollHeight;
  });
onMounted(toEnd);
watch(() => events.value.length, toEnd);
</script>
