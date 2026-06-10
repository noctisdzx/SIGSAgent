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
        <button class="big-btn primary" @click="openKeyModal">
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

    <!-- DeepSeek API key gate for live simulation -->
    <div v-if="keyModal" class="key-mask" @click.self="closeKeyModal">
      <div class="key-modal">
        <h3>{{ lang.t('输入 DeepSeek API Key', 'Enter DeepSeek API Key') }}</h3>
        <p class="key-hint">
          {{ lang.t(
            '实时模拟需要使用大模型，请填入你的 DeepSeek API Key（仅本次运行内存中使用，不会写入磁盘）。',
            'Live simulation needs an LLM. Paste your DeepSeek API key (kept in memory for this run only, never written to disk).') }}
        </p>

        <label class="key-label">{{ lang.t('API Key', 'API Key') }}</label>
        <input
          ref="keyInput"
          v-model="apiKey"
          type="password"
          class="key-input"
          placeholder="sk-..."
          autocomplete="off"
          @keyup.enter="submitKey"
        />

        <button class="key-adv-toggle" @click="showAdvanced = !showAdvanced">
          {{ showAdvanced ? '▾' : '▸' }} {{ lang.t('高级（接口地址 / 模型）', 'Advanced (base URL / model)') }}
        </button>
        <div v-if="showAdvanced" class="key-adv">
          <label class="key-label">Base URL</label>
          <input v-model="baseUrl" type="text" class="key-input" placeholder="https://api.deepseek.com/v1" />
          <label class="key-label">{{ lang.t('模型', 'Model') }}</label>
          <input v-model="model" type="text" class="key-input" placeholder="deepseek-chat" />
        </div>

        <label class="key-check">
          <input type="checkbox" v-model="doValidate" />
          {{ lang.t('进入前校验密钥（推荐）', 'Validate key before entering (recommended)') }}
        </label>

        <p v-if="keyError" class="key-error">{{ keyError }}</p>

        <div class="key-actions">
          <button class="big-btn" :disabled="submitting" @click="closeKeyModal">
            {{ lang.t('取消', 'Cancel') }}
          </button>
          <button
            v-if="llmConfigured"
            class="big-btn"
            :disabled="submitting"
            @click="useExistingKey"
            :title="lang.t('使用服务器环境中已配置的密钥', 'Use the key already configured on the server')"
          >
            {{ lang.t('用已配置密钥', 'Use existing') }}
          </button>
          <button class="big-btn primary" :disabled="submitting || !apiKey.trim()" @click="submitKey">
            {{ submitting
              ? lang.t('校验中…', 'Checking…')
              : lang.t('确定并进入', 'Confirm & Enter') }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { nextTick, onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import { usePlaybackStore } from '@/stores/playback';
import { useWorldStore } from '@/stores/world';
import { useLangStore } from '@/stores/lang';
import { api } from '@/api/endpoints';

const router = useRouter();
const pb = usePlaybackStore();
const world = useWorldStore();
const lang = useLangStore();
const picked = ref('');

// ----- DeepSeek API key gate -----
const keyModal = ref(false);
const apiKey = ref('');
const baseUrl = ref('');
const model = ref('');
const showAdvanced = ref(false);
const doValidate = ref(true);
const submitting = ref(false);
const keyError = ref('');
const llmConfigured = ref(false);
const keyInput = ref<HTMLInputElement | null>(null);

async function openKeyModal() {
  keyError.value = '';
  keyModal.value = true;
  try {
    const s = await api.llmStatus();
    llmConfigured.value = !!s.configured;
    if (s.base_url) baseUrl.value = s.base_url;
    if (s.model) model.value = s.model;
  } catch {
    llmConfigured.value = false;
  }
  await nextTick();
  keyInput.value?.focus();
}

function closeKeyModal() {
  if (submitting.value) return;
  keyModal.value = false;
}

function enterLive() {
  if (pb.active) pb.exit();      // restores liveEnabled + reloads live world
  else world.setLive(true);
  router.push('/scene');
}

async function submitKey() {
  const key = apiKey.value.trim();
  if (!key || submitting.value) return;
  submitting.value = true;
  keyError.value = '';
  try {
    await api.setLlmKey({
      api_key: key,
      base_url: baseUrl.value.trim() || undefined,
      model: model.value.trim() || undefined,
      validate: doValidate.value,
    });
    keyModal.value = false;
    enterLive();
  } catch (e: any) {
    keyError.value = e?.response?.data?.detail
      || lang.t('设置失败，请检查密钥或网络。', 'Failed to set key — check the key or network.');
  } finally {
    submitting.value = false;
  }
}

/** Proceed using whatever key the server already has configured (env). */
function useExistingKey() {
  if (submitting.value) return;
  keyModal.value = false;
  enterLive();
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
  min-height: calc(100vh - 44px);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 32px;
  padding: 40px 20px;
  background: var(--bg-base);
  position: relative;
}

/* scanline overlay */
.home::before {
  content: "";
  position: absolute;
  inset: 0;
  background: repeating-linear-gradient(
    0deg, transparent, transparent 3px,
    rgba(255,158,108,0.015) 3px, rgba(255,158,108,0.015) 4px
  );
  pointer-events: none;
  z-index: 0;
}

.home > * { position: relative; z-index: 1; }

.home-head { text-align: center; }
.home-head h1 {
  margin: 0;
  font-family: var(--font-pixel);
  font-size: 22px;
  letter-spacing: 3px;
  color: var(--accent-primary);
  text-transform: uppercase;
  text-shadow: 3px 3px 0 rgba(255,158,108,0.2);
}
.tagline {
  margin: 10px 0 0;
  color: var(--text-secondary);
  font-family: var(--font-mono);
  font-size: 13px;
  letter-spacing: 1px;
}
.tagline::before { content: "// "; color: var(--text-very-dim); }
.pick {
  margin: 14px 0 0;
  color: var(--text-very-dim);
  font-family: var(--font-mono);
  font-size: 11px;
  letter-spacing: 0.5px;
  text-transform: uppercase;
}
.pick::before { content: "> "; color: var(--accent-primary); }

.cards {
  display: flex;
  gap: 20px;
  flex-wrap: wrap;
  justify-content: center;
}
.card {
  width: 320px;
  background: var(--bg-card);
  border: 2px solid var(--border-pixel);
  padding: 24px 22px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  box-shadow: 4px 4px 0 rgba(184,151,184,0.2);
  position: relative;
}
.card::before {
  content: "";
  position: absolute;
  top: -1px; left: 8px; right: 8px;
  height: 2px;
  background: var(--accent-primary);
}
.card-icon {
  font-size: 28px;
  width: 56px; height: 56px;
  display: flex; align-items: center; justify-content: center;
  border: 2px solid var(--border-soft);
  background: var(--bg-elevated);
}
.card h2 {
  margin: 4px 0 0;
  font-family: var(--font-pixel);
  font-size: 9px;
  color: var(--accent-active);
  text-transform: uppercase;
  letter-spacing: 1px;
}
.card-desc {
  margin: 0;
  font-family: var(--font-mono);
  font-size: 12px; line-height: 1.7;
  color: var(--text-secondary);
  text-align: center;
  min-height: 60px;
}
.big-btn {
  width: 100%;
  padding: 10px 0;
  border: 2px solid var(--border-pixel);
  background: var(--bg-elevated);
  color: var(--text-primary);
  font-family: var(--font-mono);
  font-size: 12px;
  cursor: pointer;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  transition: border-color 0.1s, color 0.1s, background 0.1s;
}
.big-btn:hover:not(:disabled) {
  border-color: var(--accent-primary);
  color: var(--accent-primary);
  background: rgba(255,158,108,0.08);
}
.big-btn:disabled { opacity: 0.4; cursor: default; }
.big-btn.primary {
  border-color: var(--accent-primary);
  background: rgba(255,158,108,0.15);
  color: var(--accent-primary);
  box-shadow: 2px 2px 0 rgba(255,158,108,0.2);
}
.big-btn.primary:hover {
  background: rgba(255,158,108,0.25);
  box-shadow: 3px 3px 0 rgba(255,158,108,0.3);
}

.rec-row { display: flex; gap: 6px; width: 100%; }
.rec-select {
  flex: 1; min-width: 0;
  background: var(--bg-elevated);
  color: var(--text-secondary);
  border: 1px solid var(--border-soft);
  padding: 7px 10px;
  font-family: var(--font-mono);
  font-size: 11px;
  outline: none;
}
.rec-select:focus { border-color: var(--accent-primary); }
.micro-btn {
  background: var(--bg-elevated);
  border: 1px solid var(--border-soft);
  color: var(--text-dim);
  font-size: 14px; padding: 0 10px;
  cursor: pointer;
  font-family: var(--font-mono);
}
.micro-btn:hover { color: var(--accent-primary); border-color: var(--accent-primary); }

/* API key modal */
.key-mask {
  position: fixed; inset: 0;
  background: rgba(0,0,0,0.7);
  display: flex; align-items: center; justify-content: center;
  z-index: 1000;
}
.key-modal {
  width: 420px; max-width: calc(100vw - 32px);
  background: var(--bg-panel);
  border: 2px solid var(--accent-primary);
  padding: 22px;
  box-shadow: 6px 6px 0 rgba(255,158,108,0.2);
  position: relative;
}
.key-modal::before {
  content: "[ API KEY CONFIG ]";
  position: absolute;
  top: -11px; left: 16px;
  background: var(--bg-panel);
  padding: 0 8px;
  font-family: var(--font-pixel);
  font-size: 7px;
  color: var(--accent-primary);
  letter-spacing: 1px;
}
.key-modal h3 {
  margin: 0 0 10px;
  font-family: var(--font-pixel);
  font-size: 9px;
  color: var(--text-primary);
  text-transform: uppercase;
  letter-spacing: 1px;
}
.key-hint {
  margin: 0 0 14px;
  font-size: 11px; line-height: 1.7;
  color: var(--text-secondary);
  font-family: var(--font-mono);
}
.key-label {
  display: block; margin: 10px 0 4px;
  font-size: 10px; color: var(--text-very-dim);
  font-family: var(--font-pixel);
  letter-spacing: 0.5px;
  text-transform: uppercase;
}
.key-input {
  width: 100%; box-sizing: border-box;
  background: var(--bg-base);
  color: var(--accent-primary);
  border: 1px solid var(--border-pixel);
  padding: 8px 10px;
  font-family: var(--font-mono);
  font-size: 12px;
  outline: none;
  caret-color: var(--accent-primary);
}
.key-input:focus { border-color: var(--accent-primary); box-shadow: 0 0 0 1px var(--accent-primary); }
.key-adv-toggle {
  margin: 10px 0 0; padding: 0; background: none; border: none;
  color: var(--text-dim);
  font-family: var(--font-mono);
  font-size: 11px; cursor: pointer;
  text-transform: uppercase;
}
.key-adv-toggle:hover { color: var(--accent-primary); }
.key-adv { margin-top: 4px; }
.key-check {
  display: flex; align-items: center; gap: 7px;
  margin: 12px 0 0;
  font-size: 11px; color: var(--text-secondary);
  font-family: var(--font-mono);
  cursor: pointer;
}
.key-error {
  margin: 10px 0 0;
  font-size: 11px; line-height: 1.5;
  color: var(--accent-danger);
  font-family: var(--font-mono);
  word-break: break-word;
}
.key-error::before { content: "[ERR] "; color: var(--accent-danger-soft); }
.key-actions { display: flex; gap: 8px; margin-top: 16px; }
.key-actions .big-btn { width: auto; flex: 1; padding: 8px 0; }
</style>