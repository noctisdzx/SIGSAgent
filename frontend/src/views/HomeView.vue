<!--
  Landing / entry screen shown on startup. Lets the operator choose between:
    · Live simulation  → detach any playback, hand the world back to the live
                          feed, and jump to the scene view.
    · Playback         → pick a recorded run (rec_*.jsonl), load it into the
                          playback store, and jump to the scene view in replay
                          mode.
-->
<template>
  <div class="home">
    <header class="home-head">
      <h1>SIGSAgent</h1>
      <p class="tagline">{{ lang.t('校园多智能体模拟', 'Campus Multi-Agent Simulation') }}</p>
      <p class="pick">{{ lang.t('请选择进入方式', 'Choose how to enter') }}</p>
    </header>

    <div class="cards">
      <!-- Live simulation -->
      <section class="card">
        <div class="card-icon">▶</div>
        <h2>{{ lang.t('实时模拟', 'Live Simulation') }}</h2>
        <p class="card-desc">
          {{ lang.t(
            '进入实时世界，观察 NPC 当下的感知、决策、对话与行动。',
            'Enter the live world and watch NPCs perceive, decide, talk and act in real time.') }}
        </p>
        <button class="big-btn primary" @click="enterLive">
          {{ lang.t('进入实时模拟', 'Enter Live') }}
        </button>
      </section>

      <!-- Playback -->
      <section class="card">
        <div class="card-icon">🎬</div>
        <h2>{{ lang.t('回放记录', 'Playback') }}</h2>
        <p class="card-desc">
          {{ lang.t(
            '载入一段已录制的运行（JSONL），逐帧重放当时的场景与事件。',
            'Load a recorded run (JSONL) and replay its scene and events frame by frame.') }}
        </p>

        <div class="rec-row">
          <select v-model="picked" class="rec-select">
            <option value="" disabled>
              {{ pb.recordings.length
                ? lang.t('选择录像…', 'choose a recording…')
                : lang.t('暂无录像', 'no recordings yet') }}
            </option>
            <option v-for="r in pb.recordings" :key="r.name" :value="r.name">
              {{ r.name }} · {{ r.frames }}{{ lang.t(' 帧', 'f') }}{{ r.is_current ? lang.t('（运行中）', ' (live)') : '' }}
            </option>
          </select>
          <button class="micro-btn" :title="lang.t('刷新列表', 'Refresh')" @click="pb.refreshList()">⟳</button>
        </div>

        <button
          class="big-btn"
          :disabled="!picked || pb.loading"
          @click="enterPlayback"
        >
          {{ pb.loading ? lang.t('载入中…', 'loading…') : lang.t('载入并回放', 'Load & Replay') }}
        </button>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import { usePlaybackStore } from '@/stores/playback';
import { useWorldStore } from '@/stores/world';
import { useLangStore } from '@/stores/lang';

const router = useRouter();
const pb = usePlaybackStore();
const world = useWorldStore();
const lang = useLangStore();
const picked = ref('');

function enterLive() {
  if (pb.active) pb.exit();      // restores liveEnabled + reloads live world
  else world.setLive(true);
  router.push('/scene');
}

async function enterPlayback() {
  if (!picked.value) return;
  await pb.load(picked.value);   // sets liveEnabled=false + applies frame 0
  router.push('/scene');
}

onMounted(() => { pb.refreshList(); });
</script>

<style scoped>
.home {
  min-height: calc(100vh - 120px);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 28px;
  padding: 40px 20px;
}
.home-head { text-align: center; }
.home-head h1 {
  margin: 0;
  font-size: 40px;
  letter-spacing: 2px;
  color: var(--accent-primary);
}
.tagline { margin: 6px 0 0; color: var(--text-secondary); font-size: 15px; }
.pick { margin: 18px 0 0; color: var(--text-very-dim); font-size: 13px; }

.cards {
  display: flex;
  gap: 24px;
  flex-wrap: wrap;
  justify-content: center;
}
.card {
  width: 320px;
  background: var(--bg-card, rgba(18,24,43,0.96));
  border: 1px solid var(--border-soft, rgba(255,255,255,0.1));
  border-radius: 16px;
  padding: 26px 24px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  box-shadow: 0 8px 28px rgba(0,0,0,0.4);
}
.card-icon {
  font-size: 34px;
  width: 64px; height: 64px;
  display: flex; align-items: center; justify-content: center;
  border-radius: 50%;
  background: var(--bg-elevated, rgba(255,255,255,0.06));
}
.card h2 { margin: 4px 0 0; font-size: 20px; color: var(--text-primary, #e8ecf5); }
.card-desc {
  margin: 0;
  font-size: 13px; line-height: 1.6;
  color: var(--text-secondary, #a9b2c7);
  text-align: center;
  min-height: 64px;
}
.big-btn {
  width: 100%;
  padding: 11px 0;
  border-radius: 10px;
  border: 1px solid var(--border-soft, rgba(255,255,255,0.14));
  background: var(--bg-elevated, rgba(255,255,255,0.06));
  color: var(--text-primary, #e8ecf5);
  font-size: 14px; font-weight: 600; cursor: pointer;
  transition: background 0.15s, border-color 0.15s;
}
.big-btn:hover:not(:disabled) { background: var(--bg-card-hover, rgba(255,255,255,0.12)); }
.big-btn:disabled { opacity: 0.45; cursor: default; }
.big-btn.primary {
  background: var(--accent-active, #3b6cff);
  border-color: var(--accent-active, #3b6cff);
  color: #fff;
}
.big-btn.primary:hover { filter: brightness(1.08); }

.rec-row { display: flex; gap: 6px; width: 100%; }
.rec-select {
  flex: 1; min-width: 0;
  background: var(--bg-elevated, rgba(255,255,255,0.06));
  color: var(--text-secondary, #a9b2c7);
  border: 1px solid var(--border-soft, rgba(255,255,255,0.14));
  border-radius: 8px; padding: 8px 10px; font-size: 12.5px; outline: none;
}
.micro-btn {
  background: var(--bg-elevated, rgba(255,255,255,0.06));
  border: 1px solid var(--border-soft, rgba(255,255,255,0.14));
  color: var(--text-secondary, #a9b2c7);
  font-size: 13px; padding: 0 12px; border-radius: 8px; cursor: pointer;
}
.micro-btn:hover { color: var(--accent-primary, #6ea8ff); }
</style>
