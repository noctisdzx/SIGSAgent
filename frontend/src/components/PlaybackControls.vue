<!--
  Playback bar for recorded runs. Sits at the bottom-center of the scene graph.
  Pick a recording → load → scrub / play / change speed. While a recording is
  loaded the world store is switched to playback mode and the scene graph
  replays the recorded frames (sprites move, dialog bubbles pop, etc).
-->
<template>
  <div class="pb" :class="{ open: expanded }">
    <button class="pb-tab" @click="toggle">
      🎬 {{ pb.active ? lang.t('回放', 'Playback') : lang.t('回放记录', 'Recordings') }}
      <span v-if="pb.active" class="pb-time">{{ shortTime(pb.simTime) }}</span>
    </button>

    <div v-if="expanded" class="pb-body">
      <div class="pb-row">
        <select v-model="picked" class="pb-select">
          <option value="" disabled>{{ lang.t('选择录像…', 'choose recording…') }}</option>
          <option v-for="r in pb.recordings" :key="r.name" :value="r.name">
            {{ r.name }} · {{ r.frames }}{{ lang.t('帧', 'f') }}{{ r.is_current ? lang.t('（运行中）', ' (live)') : '' }}
          </option>
        </select>
        <button class="micro-btn" @click="pb.refreshList()">⟳</button>
        <button class="micro-btn" :disabled="!picked || pb.loading" @click="pb.load(picked)">
          {{ pb.loading ? lang.t('载入中', 'loading') : lang.t('载入', 'Load') }}
        </button>
      </div>

      <template v-if="pb.active">
        <div class="pb-row controls">
          <button class="micro-btn" @click="pb.step(-1)">⏮</button>
          <button class="micro-btn play" @click="pb.playing ? pb.pause() : pb.play()">
            {{ pb.playing ? '⏸' : '▶' }}
          </button>
          <button class="micro-btn" @click="pb.step(1)">⏭</button>
          <input
            class="pb-seek"
            type="range"
            min="0"
            :max="Math.max(0, pb.total - 1)"
            :value="pb.index"
            @input="pb.seek(Number(($event.target as HTMLInputElement).value))"
          />
          <span class="pb-idx">{{ pb.index + 1 }}/{{ pb.total }}</span>
        </div>
        <div class="pb-row speeds">
          <span class="pb-lbl">{{ lang.t('倍速', 'Speed') }}</span>
          <button
            v-for="s in [0.25, 0.5, 1, 2, 4, 8]"
            :key="s"
            class="micro-btn spd"
            :class="{ on: pb.speed === s }"
            @click="pb.setSpeed(s)"
          >{{ s }}×</button>
          <button class="micro-btn exit" @click="pb.exit()">{{ lang.t('退出回放', 'Exit') }}</button>
        </div>
        <div class="pb-clock">⏱ {{ pb.simTime }}</div>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { usePlaybackStore } from '@/stores/playback';
import { useLangStore } from '@/stores/lang';

const pb = usePlaybackStore();
const lang = useLangStore();
const expanded = ref(false);
const picked = ref('');

function toggle() {
  expanded.value = !expanded.value;
  if (expanded.value) pb.refreshList();
}
function shortTime(iso: string): string {
  try { return iso.replace('T', ' ').slice(5, 16); } catch { return iso; }
}
onMounted(() => { pb.refreshList(); });
</script>

<style scoped>
.pb {
  position: absolute;
  bottom: 16px; left: 50%; transform: translateX(-50%);
  z-index: 7;
  display: flex; flex-direction: column; align-items: center;
}
.pb-tab {
  background: rgba(18,24,43,0.96);
  border: 1px solid var(--border-soft);
  color: var(--accent-primary);
  font-size: 12px; font-weight: 600;
  padding: 6px 14px; border-radius: 18px;
  cursor: pointer;
  display: flex; align-items: center; gap: 8px;
  box-shadow: 0 4px 16px rgba(0,0,0,0.4);
}
.pb-tab:hover { background: var(--bg-elevated); }
.pb-time { color: var(--accent-warm-soft); font-family: Consolas, monospace; font-size: 11px; }

.pb-body {
  margin-top: 8px;
  width: 440px;
  background: rgba(18,24,43,0.97);
  border: 1px solid var(--border-soft);
  border-radius: 12px;
  padding: 10px 12px;
  box-shadow: 0 6px 22px rgba(0,0,0,0.5);
}
.pb-row { display: flex; align-items: center; gap: 6px; margin-bottom: 6px; }
.pb-row.controls { gap: 8px; }
.pb-select {
  flex: 1; min-width: 0;
  background: var(--bg-card); color: var(--text-secondary);
  border: 1px solid var(--border-soft); border-radius: 6px;
  padding: 4px 8px; font-size: 11.5px; outline: none;
}
.micro-btn {
  background: var(--bg-card);
  border: 1px solid var(--border-soft);
  color: var(--text-secondary);
  font-size: 11px; padding: 4px 9px; border-radius: 6px; cursor: pointer;
}
.micro-btn:hover:not(:disabled) { background: var(--bg-elevated); color: var(--accent-primary); }
.micro-btn:disabled { opacity: 0.4; cursor: default; }
.micro-btn.play { font-size: 13px; min-width: 34px; }
.micro-btn.spd.on { background: var(--accent-active); color: #fff; border-color: var(--accent-active); }
.micro-btn.exit { margin-left: auto; color: var(--accent-warn); }
.pb-seek { flex: 1; }
.pb-idx { font-family: Consolas, monospace; font-size: 11px; color: var(--text-very-dim); min-width: 56px; text-align: right; }
.pb-lbl { font-size: 11px; color: var(--text-very-dim); }
.pb-clock { font-family: Consolas, monospace; font-size: 11px; color: var(--accent-warm-soft); text-align: center; margin-top: 2px; }
.speeds { gap: 4px; }
</style>
