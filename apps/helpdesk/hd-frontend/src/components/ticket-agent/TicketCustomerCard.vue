<template>
  <!-- Customer card (NXERP data through the shared Read API). Shown only when the site setting nxerp_shared_read is on.
       A Read API failure never breaks the ticket: it shows a banner and the last known details.
       Changes go to NXERP through its command API; the shared copy catches up within a minute or two. -->
  <div
    v-if="card.data?.enabled && card.data?.linked"
    class="flex flex-col gap-2"
    data-test="customer-card"
  >
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
      data-test="customer-card-banner"
    >
      {{ __("Customer details may be out of date") }}
    </div>
    <dl class="grid grid-cols-[110px_1fr] gap-x-2 gap-y-1 text-p-sm">
      <template v-for="field in rows" :key="field.key">
        <dt class="text-ink-gray-5">{{ field.label }}</dt>
        <dd
          class="truncate text-ink-gray-8"
          :class="!field.value && 'text-ink-gray-4'"
          :data-test="`customer-card-${field.key}`"
        >
          {{ field.value || "—" }}
        </dd>
      </template>
    </dl>
    <div v-if="card.data.contact" class="flex flex-col gap-1">
      <div v-if="!editing" class="flex items-center gap-2">
        <span class="text-p-xs text-ink-gray-5">{{
          pendingNote ? __("Saved in NXERP. This card updates within a minute or two.") : ""
        }}</span>
        <Button class="ml-auto" size="sm" variant="ghost" @click="startEdit">
          {{ __("Edit contact") }}
        </Button>
      </div>
      <form v-else class="flex flex-col gap-2" @submit.prevent="save">
        <FormControl v-model="form.full_name" :label="__('Name')" type="text" />
        <FormControl v-model="form.email" :label="__('Email')" type="text" />
        <FormControl
          v-model="form.phone"
          :label="__('Phone')"
          type="text"
          data-test="customer-card-phone-input"
        />
        <div class="flex justify-end gap-2">
          <Button size="sm" variant="ghost" @click="editing = false">
            {{ __("Cancel") }}
          </Button>
          <Button
            size="sm"
            variant="solid"
            type="submit"
            :loading="saving"
            data-test="customer-card-save"
          >
            {{ __("Save in NXERP") }}
          </Button>
        </div>
      </form>
    </div>
    <p v-if="card.data.synced_at" class="text-p-xs text-ink-gray-5">
      {{ __("Updated in NXERP data at {0}", [card.data.synced_at.slice(0, 16)]) }}
    </p>
  </div>
</template>

<script setup lang="ts">
import { __ } from "@/translation.ts";
import { Badge, Button, call, createResource, FormControl, toast } from "frappe-ui";
import { computed, inject, reactive, ref } from "vue";
import { TicketSymbol } from "@/types";

const ticket = inject(TicketSymbol)!;

const card = createResource({
  url: "helpdesk.integrations.shared.api.get_customer_card",
  params: { hd_customer: ticket.value?.doc?.customer },
  auto: Boolean(ticket.value?.doc?.customer),
});

// what the agent just saved: shown at once, because the shared copy catches up a minute or two later
const saved = reactive<Record<string, string>>({});
const pendingNote = ref(false);

const rows = computed(() => {
  const fields = card.data?.fields || {};
  const contact = card.data?.contact?.fields || {};
  return [
    { key: "customer_type", label: __("Type"), value: fields.customer_type },
    { key: "customer_group", label: __("Group"), value: fields.customer_group },
    { key: "territory", label: __("Territory"), value: fields.territory },
    { key: "contact", label: __("Contact"), value: saved.full_name ?? contact.full_name },
    { key: "email", label: __("Email"), value: saved.email ?? contact.email },
    { key: "phone", label: __("Phone"), value: saved.phone ?? contact.phone },
  ];
});

const editing = ref(false);
const saving = ref(false);
const form = reactive({ full_name: "", email: "", phone: "" });
// getRandomValues exists on every page; randomUUID only on https, and a staging site may be plain http
function newActionKey(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  return "hd-ui-" + Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

// ONE key per save action: a retry of the same action reuses it, so NXERP applies the change at most once
let actionKey: string | null = null;

function startEdit() {
  const contact = card.data?.contact?.fields || {};
  form.full_name = saved.full_name ?? contact.full_name ?? "";
  form.email = saved.email ?? contact.email ?? "";
  form.phone = saved.phone ?? contact.phone ?? "";
  editing.value = true;
}

async function save() {
  const contact = card.data?.contact?.fields || {};
  const changed: Record<string, string> = {};
  for (const name of ["full_name", "email", "phone"] as const) {
    const before = saved[name] ?? contact[name] ?? "";
    if (form[name] !== before) changed[name] = form[name];
  }
  if (!Object.keys(changed).length) {
    editing.value = false;
    return;
  }
  saving.value = true;
  // the key is made BEFORE the first attempt and kept until the action succeeds, so a retry after an error cannot apply twice
  actionKey = actionKey || newActionKey();
  try {
    await call("helpdesk.integrations.shared.api.update_contact", {
      hd_customer: ticket.value?.doc?.customer,
      fields: JSON.stringify(changed),
      idempotency_key: actionKey,
    });
    actionKey = null;
    Object.assign(saved, changed);
    pendingNote.value = true;
    editing.value = false;
    toast.success(__("Saved in NXERP"));
  } catch (error: any) {
    // a refusal or an outage: NXERP did not change anything. Keep the form open; a retry reuses the same key.
    toast.error(error?.messages?.join(" ") || error?.message || __("NXERP did not apply the change"));
  } finally {
    saving.value = false;
  }
}
</script>
