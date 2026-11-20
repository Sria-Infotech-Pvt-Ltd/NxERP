<template>
  <!-- Customer card (NXERP data through the shared Read API). Shown only when the site setting nxerp_shared_read is on.
       A Read API failure never breaks the ticket: it shows a banner and the last known details. -->
  <div v-if="card.data?.enabled && card.data?.linked" class="flex flex-col gap-2">
    <div class="flex items-center gap-2">
      <p class="min-w-0 flex-1 truncate text-md font-medium text-ink-gray-7">
        {{ card.data.name || __("Customer") }}
      </p>
      <Badge
        v-if="card.data.fields?.disabled"
        theme="gray"
        variant="subtle"
        :label="__('Disabled')"
      />
    </div>
    <div
      v-if="card.data.banner"
      class="rounded bg-surface-amber-1 px-2 py-1.5 text-p-sm text-ink-amber-3"
      role="status"
    >
      {{ __("Customer details may be out of date") }}
    </div>
    <dl class="grid grid-cols-[110px_1fr] gap-x-2 gap-y-1 text-p-sm">
      <template v-for="field in rows" :key="field.key">
        <dt class="text-ink-gray-5">{{ field.label }}</dt>
        <dd class="truncate text-ink-gray-8" :class="!field.value && 'text-ink-gray-4'">
          {{ field.value || "—" }}
        </dd>
      </template>
    </dl>
    <p v-if="card.data.synced_at" class="text-p-xs text-ink-gray-5">
      {{ __("Updated in NXERP data at {0}", [card.data.synced_at.slice(0, 16)]) }}
    </p>
  </div>
</template>

<script setup lang="ts">
import { __ } from "@/translation.ts";
import { Badge, createResource } from "frappe-ui";
import { computed, inject } from "vue";
import { ITicket } from "@/pages/ticket/symbols";

const ticket = inject(ITicket) as any;

const card = createResource({
  url: "helpdesk.integrations.shared.api.get_customer_card",
  params: { hd_customer: ticket.value?.doc?.customer },
  auto: Boolean(ticket.value?.doc?.customer),
});

const rows = computed(() => {
  const fields = card.data?.fields || {};
  return [
    { key: "customer_type", label: __("Type"), value: fields.customer_type },
    { key: "customer_group", label: __("Group"), value: fields.customer_group },
    { key: "territory", label: __("Territory"), value: fields.territory },
  ];
});
</script>
