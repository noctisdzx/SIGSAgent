<!--
  Tiny chip with variants. Used for tags, taboo/comfort topics, filters,
  scene participants, etc.
-->
<template>
  <span
    :class="['chip', variant ? `chip--${variant}` : '', clickable ? 'click' : '']"
    :style="customStyle"
    :title="title"
    @click="onClick"
  >
    <slot />
  </span>
</template>

<script setup lang="ts">
import { computed } from 'vue';

const props = defineProps<{
  variant?: 'default' | 'taboo' | 'comfort' | 'filter' | 'people';
  active?: boolean;
  color?: string;        // override text color (used by group tag)
  bg?: string;           // override bg (used by group tag)
  border?: string;
  clickable?: boolean;
  title?: string;
}>();

const emit = defineEmits<{ (e: 'click'): void }>();

const customStyle = computed(() => {
  const s: Record<string, string> = {};
  if (props.color)  s.color = props.color;
  if (props.bg)     s.background = props.bg;
  if (props.border) s.border = `1px solid ${props.border}`;
  return s;
});

function onClick() { if (props.clickable) emit('click'); }
</script>

<style scoped>
.chip--filter {
  background: var(--bg-elevated);
  color: var(--text-very-dim);
  border: 1px solid var(--bg-elevated-hover);
}
.chip--people {
  background: var(--bg-elevated-hover);
  color: var(--accent-primary);
}
</style>
