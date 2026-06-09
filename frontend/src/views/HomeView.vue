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

/* ----- API key modal ----- */
.key-mask {
  position: fixed; inset: 0;
  background: rgba(0,0,0,0.55);
  display: flex; align-items: center; justify-content: center;
  z-index: 1000;
}
.key-modal {
  width: 420px; max-width: calc(100vw - 32px);
  background: var(--bg-card, rgba(18,24,43,0.98));
  border: 1px solid var(--border-soft, rgba(255,255,255,0.12));
  border-radius: 14px;
  padding: 22px 22px 18px;
  box-shadow: 0 12px 40px rgba(0,0,0,0.5);
}
.key-modal h3 { margin: 0 0 8px; font-size: 18px; color: var(--text-primary, #e8ecf5); }
.key-hint { margin: 0 0 14px; font-size: 12.5px; line-height: 1.6; color: var(--text-secondary, #a9b2c7); }
.key-label { display: block; margin: 10px 0 4px; font-size: 12px; color: var(--text-very-dim, #8893ab); }
.key-input {
  width: 100%; box-sizing: border-box;
  background: var(--bg-elevated, rgba(255,255,255,0.06));
  color: var(--text-primary, #e8ecf5);
  border: 1px solid var(--border-soft, rgba(255,255,255,0.14));
  border-radius: 8px; padding: 9px 11px; font-size: 13px; outline: none;
}
.key-input:focus { border-color: var(--accent-active, #3b6cff); }
.key-adv-toggle {
  margin: 12px 0 0; padding: 0; background: none; border: none;
  color: var(--accent-primary, #6ea8ff); font-size: 12.5px; cursor: pointer;
}
.key-adv { margin-top: 4px; }
.key-check {
  display: flex; align-items: center; gap: 7px;
  margin: 14px 0 0; font-size: 12.5px; color: var(--text-secondary, #a9b2c7); cursor: pointer;
}
.key-error {
  margin: 12px 0 0; font-size: 12.5px; line-height: 1.5;
  color: #ff8585; word-break: break-word;
}
.key-actions { display: flex; gap: 10px; margin-top: 18px; }
.key-actions .big-btn { width: auto; flex: 1; padding: 9px 0; }
</style>
