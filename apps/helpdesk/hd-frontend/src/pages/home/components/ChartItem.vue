<template>
  <div class="h-full w-full rounded-4 border border-outline-gray-1">
    <AgentTicketsCard v-if="item.chart == 'agent_tickets'" :data="item.data" />
    <LineChartCard
      v-if="item.chart == 'avg_first_response_time'"
      :title="__('Avg. First Response')"
      api-url="helpdesk.api.agent_home.agent_home.get_avg_first_response_time"
      :data="item.data"
      tone="red"
    />
    <LineChartCard
      v-if="item.chart == 'avg_resolution_time'"
      :title="__('Avg. Resolution')"
      api-url="helpdesk.api.agent_home.agent_home.get_avg_resolution_time"
      :data="item.data"
      tone="violet"
    />
    <RecentFeedback v-if="item.chart == 'recent_feedback'" :data="item.data" />
    <AvgTimeMetrics v-if="item.chart == 'avg_time_metrics'" :data="item.data" />
    <PendingTickets v-if="item.chart == 'pending_tickets'" :data="item.data" />
    <RecentActivity v-if="item.chart == 'recent_activity'" :data="item.data" />
  </div>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { type PropType } from "vue";
import LineChartCard from "../../../components/LineChartCard.vue";
import AgentTicketsCard from "./AgentTicketsCard.vue";
import AvgTimeMetrics from "./AvgTimeMetrics.vue";
import PendingTickets from "./PendingTickets.vue";
import RecentActivity from "./RecentActivity.vue";
import RecentFeedback from "./RecentFeedback.vue";

interface Item {
  chart: string;
  data: any;
}

const props = defineProps({
  item: {
    type: Object as PropType<Item>,
    required: true,
  },
});
</script>
