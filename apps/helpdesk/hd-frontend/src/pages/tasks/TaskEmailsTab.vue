<template>
  <div v-if="task.emails.length" class="min-h-0 flex-1 overflow-y-auto">
    <ol class="mx-auto w-full max-w-4xl space-y-4 px-5 py-5">
      <li
        v-for="email in task.emails"
        :key="email.name"
        class="rounded-lg border border-outline-gray-2 bg-surface-white"
      >
        <div class="flex items-start gap-3 border-b px-4 py-3">
          <Avatar
            :label="email.user?.full_name || email.sender_full_name || '?'"
            v-bind="email.user?.user_image ? { image: email.user.user_image } : {}"
            size="md"
          />
          <div class="min-w-0 flex-1 text-p-sm">
            <div class="flex flex-wrap items-center gap-x-2">
              <span class="font-medium text-ink-gray-8">
                {{ email.user?.full_name || email.sender_full_name || email.sender }}
              </span>
              <Tooltip :text="formatDateTime(email.creation)">
                <span class="whitespace-nowrap text-ink-gray-5">
                  {{ dayjs(email.creation).fromNow() }}
                </span>
              </Tooltip>
            </div>
            <div class="text-ink-gray-6 break-words">
              {{ __("To") }}: {{ email.recipients }}
              <template v-if="email.cc"> · {{ __("Cc") }}: {{ email.cc }}</template>
              <template v-if="email.bcc"> · {{ __("Bcc") }}: {{ email.bcc }}</template>
            </div>
            <div class="mt-0.5 text-ink-gray-8">{{ email.subject }}</div>
          </div>
        </div>
        <!-- Sanitised server-side (sanitize_html) in get_emails. -->
        <div
          class="prose-f max-w-none px-4 py-3 text-p-sm text-ink-gray-8"
          v-html="email.content"
        />
      </li>
    </ol>
  </div>
  <div v-else class="grid flex-1 place-items-center px-5 py-16 text-center">
    <div class="space-y-2">
      <EmailIcon class="mx-auto size-10 text-ink-gray-4" />
      <div class="text-md-medium text-ink-gray-8">
        {{ __("No emails yet") }}
      </div>
      <p class="max-w-sm text-p-base text-ink-gray-6">
        {{ __("Replies sent from this task appear here. Use Reply on the Activity tab.") }}
      </p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { EmailIcon } from "@/components/icons";
import { __ } from "@/translation";
import { Avatar, dayjs, Tooltip } from "frappe-ui";
import type { TaskDetail } from "./taskMeta";

defineProps<{ task: TaskDetail }>();

const formatDateTime = (value: string) =>
  dayjs(value).format("D MMM YYYY, h:mm A");
</script>
