import { createResource } from "frappe-ui";
import { defineStore } from "pinia";
import { computed } from "vue";

// Tickets assigned to the signed-in agent that they have not opened yet.
// Opening a ticket marks it seen, so the count is refreshed on navigation and on a slow timer.
export const useUnseenStore = defineStore("unseen", () => {
  const resource = createResource({
    url: "helpdesk.api.unseen.get_unseen_assigned_count",
    cache: "unseen-assigned-count",
    auto: false,
    // customers and non-agents are refused by the API; a missing badge is the right outcome, not a toast
    onError: () => {},
  });

  const count = computed<number>(() => Number(resource.data) || 0);

  let timer: ReturnType<typeof setInterval> | undefined;

  function start(everyMs = 60_000) {
    resource.reload();
    if (!timer) timer = setInterval(() => resource.reload(), everyMs);
  }

  function stop() {
    if (timer) clearInterval(timer);
    timer = undefined;
  }

  return { count, start, stop, refresh: () => resource.reload() };
});
