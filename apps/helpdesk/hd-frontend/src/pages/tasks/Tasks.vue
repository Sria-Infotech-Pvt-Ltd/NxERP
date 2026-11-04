<template>
  <div>
    <LayoutHeader>
      <template #left-header>
        <ViewBreadcrumbs
          :label="__('Tasks')"
          route-name="Tasks"
          :options="dropdownOptions"
          :dropdown-actions="(view) => viewActions(view, viewDialogConfig)"
          :current-view="currentView"
        />
      </template>
      <template #right-header>
        <Button
          class="rtl:flex-row-reverse"
          :label="__('Create')"
          theme="gray"
          variant="solid"
          @click="showNew = true"
        >
          <template #prefix>
            <LucidePlus class="h-4 w-4" />
          </template>
        </Button>
      </template>
    </LayoutHeader>
    <div class="relative flex min-h-0 flex-1">
      <div class="flex min-h-0 min-w-0 flex-1 flex-col">
        <ListViewBuilder ref="listViewRef" :options="options" />
      </div>
      <Transition
        enter-active-class="transition duration-200 ease-out"
        enter-from-class="translate-x-4 opacity-0"
        leave-active-class="transition duration-150 ease-in"
        leave-to-class="translate-x-4 opacity-0"
      >
        <aside
          v-if="selectedTaskId"
          class="absolute inset-0 z-10 flex min-h-0 flex-col bg-surface-white lg:static lg:inset-auto lg:z-auto lg:w-[28rem] lg:shrink-0 lg:border-s lg:border-outline-gray-2 lg:bg-transparent"
          :aria-label="__('Task details')"
        >
          <div class="min-h-0 flex-1">
            <TaskDetail
              :key="selectedTaskId"
              :task-id="selectedTaskId"
              closable
              @close="closeTask"
              @changed="listViewRef?.reload()"
            />
          </div>
        </aside>
      </Transition>
    </div>
    <ViewModal
      v-if="viewDialogConfig.show"
      v-model="viewDialogConfig"
      @update="onViewModalUpdate"
    />
    <NewTaskDialog v-model="showNew" @created="onCreated" />
    <TaskBulkDialog
      v-model="bulkDialog.show"
      :mode="bulkDialog.mode"
      :names="bulkDialog.names"
      @done="reset(true)"
    />
  </div>
</template>

<script setup lang="ts">
import { LayoutHeader, ListViewBuilder } from "@/components";
import IndicatorIcon from "@/components/icons/IndicatorIcon.vue";
import ViewBreadcrumbs from "@/components/ViewBreadcrumbs.vue";
import ViewModal from "@/components/ViewModal.vue";
import { currentView, useView } from "@/composables/useView";
import { useUserStore } from "@/stores/user";
import { __ } from "@/translation";
import { View } from "@/types";
import { Badge, usePageMeta } from "frappe-ui";
import { computed, h, onMounted, reactive, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import LucideAlarmClock from "~icons/lucide/alarm-clock";
import LucideAlignJustify from "~icons/lucide/align-justify";
import LucideCalendar from "~icons/lucide/calendar";
import LucideListChecks from "~icons/lucide/list-checks";
import LucidePlus from "~icons/lucide/plus";
import LucideUser from "~icons/lucide/user";
import LucideUserX from "~icons/lucide/user-x";
import NewTaskDialog from "./NewTaskDialog.vue";
import TaskBulkDialog from "./TaskBulkDialog.vue";
import TaskDetail from "./TaskDetail.vue";
import TaskUser from "./TaskUser.vue";
import {
  dueLabel,
  isOverdue,
  priorityBadge,
  priorityBadgeClass,
  statusDot,
  viewFilters,
  viewLabels,
  type TaskView,
} from "./taskMeta";

const router = useRouter();
const route = useRoute();
const { getUser } = useUserStore();

const {
  getCurrentUserViews,
  publicViews,
  pinnedViews,
  findView,
  standardViews,
  viewActions,
  handleView,
  resetViewDialog,
} = useView("HD Task");

const listViewRef = ref(null);
const showNew = ref(false);
const bulkDialog = reactive({
  show: false,
  mode: "assign" as "assign" | "status",
  names: [] as string[],
});

const activeView = computed(() => findView(route.query.view as string).value);
const hasActiveFilters = computed(
  () => Object.keys(listViewRef.value?.list?.params?.filters || {}).length > 0
);

const selectBannerActions = [
  {
    label: __("Assign"),
    icon: "lucide-user-plus",
    inline: true,
    onClick: (selections: Set<string>) => openBulk("assign", selections),
  },
  {
    label: __("Status"),
    icon: "lucide-circle-dot",
    inline: true,
    onClick: (selections: Set<string>) => openBulk("status", selections),
  },
];

function openBulk(mode: "assign" | "status", selections: Set<string>) {
  bulkDialog.mode = mode;
  bulkDialog.names = Array.from(selections);
  bulkDialog.show = true;
}

// The open task lives in the URL so Back, refresh and shared links keep the panel.
const selectedTaskId = computed(() => route.query.task as string | undefined);

function openTask(name: string) {
  if (name === selectedTaskId.value) return;
  router.push({ name: route.name, query: { ...route.query, task: name } });
}

function closeTask() {
  router.push({ name: route.name, query: { ...route.query, task: undefined } });
}

const options = computed(() => ({
  doctype: "HD Task",
  skipDefaultViewFilters: true,
  hideQuickFilters: true,
  onRowClick: openTask,
  columnConfig: {
    subject: {
      custom: ({ item, row }) =>
        h(
          "span",
          {
            class: [
              "truncate text-base",
              row.name === selectedTaskId.value
                ? "font-semibold text-ink-gray-9"
                : "text-ink-gray-8",
            ],
          },
          item
        ),
    },
    status: {
      custom: ({ item }) =>
        h("div", { class: "flex items-center gap-1.5 justify-start w-full" }, [
          h(IndicatorIcon, { class: statusDot[item] }),
          h("span", { class: "truncate flex-1 text-base" }, __(item)),
        ]),
    },
    priority: {
      custom: ({ item }) =>
        item
          ? h(Badge, {
              label: __(item),
              theme: priorityBadge[item]?.theme,
              variant: priorityBadge[item]?.variant,
              class: priorityBadgeClass[item],
            })
          : null,
    },
    assigned_to: {
      custom: ({ item }) => {
        if (!item) return null;
        const { full_name, user_image } = getUser(item);
        return h(TaskUser, { user: { name: item, full_name, user_image } });
      },
    },
    due_date: {
      custom: ({ row }) =>
        h(
          "span",
          {
            class: [
              "truncate text-p-sm",
              isOverdue(row) ? "font-medium text-ink-red-8" : "text-ink-gray-7",
            ],
          },
          dueLabel(row) || "—"
        ),
    },
  },
  selectable: true,
  showSelectBanner: true,
  selectBannerActions,
  emptyState: {
    title: __("No tasks found"),
    icon: h(LucideListChecks, { class: "h-10 w-10" }),
    description:
      activeView.value?.public || activeView.value?.pinned
        ? __(
            "No tasks found for this view. Try adjusting your filters or creating a new view."
          )
        : hasActiveFilters.value
        ? __(
            "No tasks found for the applied filters. Try adjusting or clearing your filters."
          )
        : undefined,
  },
  hideColumnSetting: false,
}));

function reset(reload = false) {
  listViewRef.value?.unselectAll();
  if (reload) listViewRef.value?.reload();
}

function onCreated(name: string) {
  listViewRef.value?.reload();
  openTask(name);
}

// Fixed views are plain filters on the URL, so they need no saved HD View records.
const fixedViews: { key: TaskView; icon: any }[] = [
  { key: "all", icon: LucideListChecks },
  { key: "my", icon: LucideUser },
  { key: "overdue", icon: LucideAlarmClock },
  { key: "due_this_week", icon: LucideCalendar },
  { key: "unassigned", icon: LucideUserX },
];
const labels = viewLabels();

function openFixedView(key: TaskView) {
  const filters = viewFilters(key);
  currentView.value = {
    label: key === "all" ? __("List") : labels[key],
    icon:
      key === "all"
        ? LucideAlignJustify
        : fixedViews.find((v) => v.key === key)!.icon,
  };
  router.push({
    name: "Tasks",
    query: filters.length
      ? { tview: key, filters: JSON.stringify(filters) }
      : {},
  });
}

let viewDialogConfig = reactive({
  show: false,
  view: {
    label: "",
    icon: "",
    name: "",
  },
  mode: "create",
});

const dropdownOptions = computed(() => {
  const items = [
    {
      group: __("Default Views"),
      items: fixedViews.map(({ key, icon }) => ({
        label: labels[key],
        icon,
        onClick: () => openFixedView(key),
      })),
    },
  ];

  if (getCurrentUserViews.value?.length !== 0) {
    items.push({
      group: __("Saved Views"),
      items: parseViews(getCurrentUserViews.value),
    });
  }
  if (pinnedViews.value?.length !== 0) {
    items.push({
      group: __("Private Views"),
      items: parseViews(pinnedViews.value),
    });
  }

  const allPublicViews = [
    ...(standardViews.value || []),
    ...(publicViews.value || []),
  ];
  const uniquePublicViews = Array.from(
    new Map(allPublicViews.map((v) => [v.name, v])).values()
  );
  items.push({
    group: __("Public Views"),
    items: parseViews(uniquePublicViews),
  });

  items.push({
    group: __("Create View"),
    hideLabel: true,
    items: [
      {
        label: __("Create View"),
        icon: "lucide-plus",
        onClick: () => {
          resetViewDialog(viewDialogConfig);
          viewDialogConfig.show = true;
        },
      },
    ],
  });

  return items;
});

function parseViews(views: View[]) {
  return views?.map((view) => ({
    ...view,
    onClick: () => {
      currentView.value = { label: view.label, icon: view.icon };
      router.push({ name: view.route_name, query: { view: view.name } });
    },
  }));
}

function onViewModalUpdate(viewInfo: any, action: string) {
  handleView(viewInfo, action, viewDialogConfig, () => listViewRef.value?.list);
}

onMounted(() => {
  const fixed = fixedViews.find((v) => v.key === route.query.tview);
  if (fixed && !route.query.view) {
    currentView.value = { label: labels[fixed.key], icon: fixed.icon };
  } else if (!route.query.view) {
    currentView.value = { label: __("List"), icon: LucideAlignJustify };
  }
});

usePageMeta(() => ({ title: __("Tasks") }));
</script>
