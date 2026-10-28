<template>
  <img :src="src" alt="NXERP" width="118" height="118" />
</template>

<script setup lang="ts">
// A runtime URL (served by the app's static files), so the build does not try to bundle it.
const src = "/assets/helpdesk/nxerp_login/images/nxerp-mark.png";
</script>
