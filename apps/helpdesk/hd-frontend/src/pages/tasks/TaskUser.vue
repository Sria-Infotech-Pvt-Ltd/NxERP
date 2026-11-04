<template>
  <div class="flex min-w-0 items-center gap-2">
    <template v-if="user">
      <Avatar :label="user.full_name" :image="user.user_image" size="sm" />
      <span class="truncate text-p-sm text-ink-gray-8">{{
        user.full_name
      }}</span>
    </template>
    <span v-else class="text-p-sm text-ink-gray-5">{{ __("Unassigned") }}</span>
  </div>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { Avatar } from "frappe-ui";
import type { TaskUser as TaskUserData } from "./taskMeta";

defineProps<{ user?: TaskUserData | null }>();
</script>
