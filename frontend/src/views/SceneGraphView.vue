<!--
  Scene topology view.
  Renders the 16-room adjacency graph from `/api/scene/graph`.
  Click a room → side panel shows room metadata + agents currently inside.
-->
<template>
  <div class="scene-page">
    <div class="scene-graph">
      <NetworkGraph
        ref="graphRef"
        :nodes="vNodesAll"
        :edges="vEdgesAll"
        :options="opts"
        @select-node="onSelectNode"
        @ready="onNetReady"
      />

      <!-- "talking" indicator bubbles above NPC sprites (placeholder only;
           the actual lines show in the chat log when you click the NPC). -->
      <div class="bubble-layer">
        <div
          v-for="b in bubbles"
          :key="b.key"
          v-show="b.show"
          class="bubble"
          :class="`bubble--${b.kind}`"
          :style="{ left: b.x + 'px', top: b.y + 'px' }"
          :title="b.kind === 'thought'
            ? lang.t('点击该 NPC 查看内心独白', 'click the NPC to read the inner monologue')
            : lang.t('点击该 NPC 查看对话', 'click the NPC to read the conversation')"
        >
          <span v-if="b.kind === 'thought'" class="bubble-think">💭</span>
          <span v-else class="bubble-dots"><i /><i /><i /></span>
        </div>
      </div>

      <PlaybackControls />
      <div class="stats">
        <span>{{ lang.t('房间', 'Rooms') }}
          <b>{{ rooms.length }}</b></span>
        <span>{{ lang.t('相邻边', 'Adjacencies') }}
          <b>{{ vEdges.length }}</b></span>
        <span>{{ lang.t('追踪中', 'Tracking') }}
          <b>{{ trackedAgents.length }}</b></span>
        <span v-if="world.lastTickAt" class="sim-clock">
          ⏱ {{ shortTime(world.lastTickAt) }}
        </span>
      </div>

      <div class="tracker-panel">
        <div class="tracker-header">
          <strong>{{ lang.t('NPC 实时追踪', 'Track NPC moves') }}</strong>
          <div class="tracker-actions">
            <button @click="trackAll" class="micro-btn">{{ lang.t('全部', 'All') }}</button>
            <button @click="trackNone" class="micro-btn">{{ lang.t('清空', 'None') }}</button>
          </div>
        </div>
        <input
          v-model="filterText"
          :placeholder="lang.t('按姓名/id 过滤…', 'filter by name/id…')"
          class="tracker-filter"
        />
        <div class="tracker-list">
          <label v-for="a in filteredAgents" :key="String(a.id)" class="tracker-item">
            <input
              type="checkbox"
              :checked="trackedSet.has(String(a.id))"
              @change="toggleTrack(String(a.id))"
            />
            <span class="dot" :style="{ background: colorForAgent(String(a.id)) }"></span>
            <span class="tracker-name">{{ npcName(a) }}</span>
            <span class="tracker-loc">@{{ roomLabel(currentLocation(String(a.id))) }}</span>
          </label>
          <div v-if="!filteredAgents.length" class="empty-small">
            {{ lang.t('无匹配的 NPC', 'no NPC matched') }}
          </div>
        </div>
      </div>

      <div class="topright-actions">
        <button class="ctrl-btn" @click="showHeatPanel = !showHeatPanel">
          🔥 {{ showHeatPanel ? lang.t('收起', 'Hide') : lang.t('热力', 'Heat') }}
        </button>
        <button class="ctrl-btn" @click="showTunePanel = !showTunePanel">
          {{ showTunePanel ? lang.t('收起调节', 'Hide') : lang.t('⚙ 视图调节', '⚙ Tune') }}
        </button>
        <button class="ctrl-btn" @click="resetView">
          {{ lang.t('重置视图', 'Reset View') }}
        </button>
      </div>

      <!-- Heat-map controls: each layer can be toggled independently;
           the bottom row exposes the current totals and a reset button. -->
      <div v-if="showHeatPanel" class="heat-panel">
        <div class="heat-header">
          <strong>🔥 {{ lang.t('热力图层', 'Heat Layers') }}</strong>
          <button class="micro-btn" @click="clearHeat">
            {{ lang.t('清零', 'Reset') }}
          </button>
        </div>
        <label class="heat-row">
          <input type="checkbox" v-model="showMoveHeat" />
          <span class="heat-sw move"></span>
          {{ lang.t('移动路线热力', 'Movement routes') }}
          <span class="heat-num">·  max {{ heat.maxMoveCount }}</span>
        </label>
        <label class="heat-row">
          <input type="checkbox" v-model="showDwellHeat" />
          <span class="heat-sw dwell"></span>
          {{ lang.t('驻留时间热力', 'Dwell time') }}
          <span class="heat-num">·  max {{ heat.maxDwellCount }}</span>
        </label>
        <label class="heat-row">
          <input type="checkbox" v-model="showHotRoomGlow" />
          <span class="heat-sw glow"></span>
          {{ lang.t('当前最热房间发光', 'Glow on hottest room now') }}
        </label>
        <div v-if="hottestCurrentRoom" class="heat-hot-now">
          {{ lang.t('当前最多人', 'Most NPCs now') }}:
          <b>{{ roomLabel(hottestCurrentRoom) }}</b>
          <span class="heat-num">({{ roomPopulation[hottestCurrentRoom] }})</span>
        </div>
        <div class="heat-hint">
          {{ lang.t(
            '边粗细/颜色 = 累计穿过次数；房间发光 = 累计驻留量；金色边框 = 当前人数最多',
            'Edge width/color = cumulative traversals; room glow = cumulative dwell; gold border = most NPCs now'
          ) }}
        </div>
      </div>

      <!-- View tuning panel: change sizes & spacing without losing the camera -->
      <div v-if="showTunePanel" class="tune-panel" :class="{ 'shift-below-heat': showHeatPanel }">
        <div class="tune-header">
          <strong>{{ lang.t('视图调节', 'View tuning') }}</strong>
          <button class="micro-btn" @click="resetSizes">{{ lang.t('恢复默认', 'Defaults') }}</button>
        </div>
        <div class="tune-row">
          <label>{{ lang.t('房间间距', 'Room spacing') }}</label>
          <input type="range" min="8" max="60" step="1" v-model.number="roomPosScale" />
          <span class="tune-val">{{ roomPosScale }}</span>
        </div>
        <div class="tune-row">
          <label>{{ lang.t('房间大小', 'Room size') }}</label>
          <input type="range" min="4" max="80" step="1" v-model.number="roomSize" />
          <span class="tune-val">{{ roomSize }}</span>
        </div>
        <div class="tune-row">
          <label>{{ lang.t('NPC 大小', 'NPC size') }}</label>
          <input type="range" min="3" max="20" step="1" v-model.number="npcSize" />
          <span class="tune-val">{{ npcSize }}</span>
        </div>
        <label class="tune-toggle no-border">
          <input type="checkbox" v-model="useSprites" />
          <span>{{ lang.t('用像素小人头像', 'Pixel sprite avatars') }}</span>
        </label>
        <div class="tune-row">
          <label>{{ lang.t('移动速度', 'Move speed') }}</label>
          <input type="range" min="400" max="6000" step="100" v-model.number="moveAnimMs" />
          <span class="tune-val">{{ (moveAnimMs / 1000).toFixed(1) }}s</span>
        </div>
        <div class="tune-row">
          <label>{{ lang.t('物品大小', 'Item size') }}</label>
          <input type="range" min="2" max="16" step="1" v-model.number="itemSize" />
          <span class="tune-val">{{ itemSize }}</span>
        </div>
        <div class="tune-row">
          <label>{{ lang.t('NPC 离场景距离', 'NPC ↔ room gap') }}</label>
          <input type="range" min="0" max="120" step="1" v-model.number="npcRoomGap" />
          <span class="tune-val">{{ npcRoomGap }}</span>
        </div>
        <label class="tune-toggle">
          <input type="checkbox" v-model="autoScaleOnZoom" />
          <span>{{ lang.t('缩小时自动放大节点', 'Auto-scale nodes on zoom-out') }}</span>
          <span class="tune-val">×{{ zoomBoost.toFixed(2) }}</span>
        </label>
        <template v-if="autoScaleOnZoom">
          <div class="tune-row sub">
            <label>{{ lang.t('房间放大上限', 'Room cap') }}</label>
            <input type="range" min="1" max="16" step="0.5" v-model.number="maxRoomBoost" />
            <span class="tune-val">×{{ maxRoomBoost }}</span>
          </div>
          <div class="tune-row sub">
            <label>{{ lang.t('NPC 放大上限', 'NPC cap') }}</label>
            <input type="range" min="1" max="8" step="0.5" v-model.number="maxNpcBoost" />
            <span class="tune-val">×{{ maxNpcBoost }}</span>
          </div>
          <div class="tune-row sub">
            <label>{{ lang.t('物品放大上限', 'Item cap') }}</label>
            <input type="range" min="1" max="8" step="0.5" v-model.number="maxItemBoost" />
            <span class="tune-val">×{{ maxItemBoost }}</span>
          </div>
        </template>
        <div class="tune-divider">{{ lang.t('校园底图', 'Campus map') }}</div>
        <label class="tune-toggle no-border">
          <input type="checkbox" v-model="mapVisible" />
          <span>{{ lang.t('显示底图', 'Show map') }}</span>
        </label>
        <template v-if="mapVisible">
          <div class="tune-row sub">
            <label>{{ lang.t('透明度', 'Opacity') }}</label>
            <input type="range" min="0" max="1" step="0.05" v-model.number="mapOpacity" />
            <span class="tune-val">{{ mapOpacity.toFixed(2) }}</span>
          </div>
          <div class="tune-row sub">
            <label>{{ lang.t('缩放', 'Scale') }}</label>
            <input type="range" :min="mapScaleMin" :max="mapScaleMax" :step="mapScaleStep" v-model.number="mapScale" />
            <span class="tune-val">{{ mapScale.toFixed(3) }}</span>
          </div>
          <div class="tune-row sub">
            <label>{{ lang.t('水平位移', 'Offset X') }}</label>
            <input type="range" :min="-mapOffsetRange" :max="mapOffsetRange" step="1" v-model.number="mapX" />
            <span class="tune-val">{{ Math.round(mapX) }}</span>
          </div>
          <div class="tune-row sub">
            <label>{{ lang.t('垂直位移', 'Offset Y') }}</label>
            <input type="range" :min="-mapOffsetRange" :max="mapOffsetRange" step="1" v-model.number="mapY" />
            <span class="tune-val">{{ Math.round(mapY) }}</span>
          </div>
        </template>
        <button class="micro-btn full" @click="resetRoomPositions">
          {{ lang.t('重置房间位置', 'Reset room positions') }}
        </button>
        <div class="tune-hint">
          {{ lang.t('拖动房间到任意位置，会自动保存（重启后保留）。视图设置存于本地。',
            'Drag rooms anywhere — saved automatically (kept after restart). View prefs stored locally.') }}
        </div>
      </div>
    </div>

    <aside class="scene-side">
      <!-- NPC inline panel: GOAP behaviour chain + conversation log -->
      <div v-if="selectedNpcId" class="npc-panel">
        <div class="npc-panel-head">
          <div class="npc-panel-title">
            <span class="dot" />{{ selectedNpcName }}
          </div>
          <div class="npc-panel-actions">
            <button class="mini-btn" @click="openNpcProfile">{{ lang.t('完整档案', 'Profile') }}</button>
            <button class="mini-btn" @click="closeNpcPanel">✕</button>
          </div>
        </div>

        <div class="section-title">{{ lang.t('GOAP 行为规划', 'GOAP Plan') }}</div>
        <div v-if="npcDecision" class="goap-box">
          <div class="goap-row">
            <span class="goap-k">{{ lang.t('日程活动', 'Activity') }}</span>
            <span class="goap-v">{{ activityText }}
              <em class="goap-kind">{{ npcDecision.payload?.slot_kind }}</em>
              <span v-if="activityRaw" class="goap-raw">{{ lang.t('原始日程', 'raw') }}: {{ activityRaw }}</span>
            </span>
          </div>
          <div class="goap-row">
            <span class="goap-k">{{ lang.t('目标状态', 'Goal') }}</span>
            <span class="goap-v mono">
              <template v-if="npcDecision.payload?.goal && Object.keys(npcDecision.payload.goal).length">
                <span v-for="(gv, gk) in npcDecision.payload.goal" :key="gk" class="goal-chip">{{ gk }} = {{ gv }}</span>
              </template>
              <template v-else>—</template>
            </span>
          </div>
          <div class="goap-arrow">↓ {{ lang.t('规划为行为链', 'planned into action chain') }}</div>
          <div class="chain">
            <template v-if="(npcDecision.payload?.plan || []).length">
              <div
                v-for="(s, i) in npcDecision.payload.plan"
                :key="i"
                class="chain-step"
                :class="{ active: npcDecision.payload?.step && npcDecision.payload.step.action_id === s.action_id && i === 0 }"
              >
                <span class="chain-idx">{{ i + 1 }}</span>
                <span class="chain-label">{{ s.label || s.action_id }}</span>
                <span class="chain-cost">c{{ s.cost }}</span>
              </div>
            </template>
            <div v-else class="empty">
              {{ lang.t('（无计划 — 执行：', '(no plan — executing: ') }}{{ npcDecision.payload?.step?.action_id || 'idle' }}）
            </div>
          </div>
          <div v-if="npcDecision.payload?.step" class="goap-exec">
            {{ lang.t('当前执行', 'Executing') }}:
            <strong>{{ npcDecision.payload.step.action_id }}</strong>
            <span v-if="npcDecision.payload.step.params && Object.keys(npcDecision.payload.step.params).length" class="mono">
              {{ JSON.stringify(npcDecision.payload.step.params) }}
            </span>
          </div>
        </div>
        <div v-else class="empty">{{ lang.t('（等待该 NPC 的下一次决策…）', '(waiting for next decision…)') }}</div>

        <div class="section-title">{{ lang.t('对话记录', 'Chat Log') }}</div>
        <div v-if="npcChat.length" class="chatlog">
          <div v-for="t in npcChat" :key="t.key" class="chat-turn">
            <div class="chat-meta">
              <span class="chat-time">{{ t.ts }}</span>
              <span class="chat-partner">↔ {{ t.partner }}</span>
              <span v-if="t.topic" class="chat-topic">{{ t.topic }}</span>
            </div>
            <div class="chat-line mine"><b>{{ selectedNpcName }}:</b> {{ t.mine }}</div>
            <div v-if="t.theirs" class="chat-line theirs"><b>{{ t.partner }}:</b> {{ t.theirs }}</div>
          </div>
        </div>
        <div v-else class="empty">{{ lang.t('（暂无对话）', '(no conversation yet)') }}</div>

        <div class="section-title">{{ lang.t('内心独白', 'Monologue') }}</div>
        <div v-if="npcMutters.length" class="mutterlog">
          <div v-for="m in npcMutters" :key="m.key" class="mutter-turn">
            <span class="mutter-time">{{ m.ts }}</span>
            <span class="mutter-line">💭 {{ m.line }}</span>
            <span v-if="m.mood" class="mutter-mood">{{ m.mood }}</span>
          </div>
        </div>
        <div v-else class="empty">{{ lang.t('（暂无独白）', '(no monologue yet)') }}</div>
      </div>

      <RoomHeatPanel
        :rooms="rooms"
        :world-agents="world.worldSnapshot?.agents || null"
        :highlight-uid="selectedUid"
        :filter-agent-ids="trackedAgents"
        @select-room="onSelectNode"
      />

      <div class="panel-header">
        <h2>{{ lang.t('房间详情', 'Room Detail') }}</h2>
      </div>
      <div class="panel-content" v-if="!selected">
        <div class="placeholder">
          {{ lang.t('点击图谱中的房间查看详情。', 'Click a room to inspect.') }}
        </div>
      </div>
      <div class="panel-content" v-else>
        <div class="room-name">{{ selected.name }}</div>
        <div class="kv"><span class="k">UID</span><span class="v mono">{{ selected.uid }}</span></div>
        <div class="kv"><span class="k">{{ lang.t('容量', 'Containment') }}</span>
          <span class="v">{{ selected.containment }}</span></div>
        <div class="kv"><span class="k">{{ lang.t('坐标', 'Position') }}</span>
          <span class="v mono">{{ (selected.position || []).join(', ') }}</span></div>

        <div class="section-title">{{ lang.t('标签', 'Tags') }}</div>
        <Chip v-for="t in (selected.tag || [])" :key="t" variant="default">{{ t }}</Chip>

        <div class="section-title">{{ lang.t('描述', 'Description') }}</div>
        <div class="desc">{{ selected.description }}</div>

        <div class="section-title" v-if="(selected.furniture || []).length">
          {{ lang.t('家具', 'Furniture') }}
        </div>
        <div v-if="(selected.furniture || []).length" class="kv-block">
          <div v-for="f in selected.furniture" :key="f.name" class="kv">
            <span class="k">{{ f.name }}</span>
            <span class="v">×{{ f.num }}</span>
          </div>
        </div>

        <div class="section-title">{{ lang.t('相邻房间', 'Adjacent') }}</div>
        <Chip
          v-for="uid in (selected.adjacent || [])"
          :key="uid"
          variant="people"
          :clickable="true"
          @click="jumpToRoom(uid)"
        >
          {{ roomLabel(uid) }}
        </Chip>

        <div class="section-title">{{ lang.t('当前在此的 NPC', 'NPCs currently here') }}</div>
        <Chip
          v-for="a in agentsHere"
          :key="String(a.id)"
          variant="people"
          :clickable="true"
          @click="$router.push(`/agent/${a.id}`)"
        >
          {{ npcName(a) }}
        </Chip>
        <div v-if="!agentsHere.length" class="empty">
          {{ lang.t('（暂无 NPC 在此）', '(no NPC here)') }}
        </div>

        <div class="section-title">{{ lang.t('物品（在此 / 被携带）', 'Items (here / carried)') }}</div>
        <div v-if="itemsHere.length" class="kv-block">
          <div v-for="it in itemsHere" :key="it.id" class="kv">
            <span class="k">🪑 {{ itemDisplayLabel(it) }}</span>
            <span class="v">
              <template v-if="it.carrier_id">
                {{ lang.t('被', 'carried by') }}
                <em>{{ (agents.list.find(a => String(a.id) === it.carrier_id) || {}).name || it.carrier_id }}</em>
              </template>
              <template v-else>{{ lang.t('放置', 'placed') }}</template>
            </span>
          </div>
        </div>
        <div v-else class="empty">{{ lang.t('（无物品）', '(no items)') }}</div>

        <div class="section-title">
          {{ lang.t('此处事件（最近）', 'Events here (recent)') }}
        </div>
        <div v-if="roomTriplets.length" class="triplet-list">
          <div
            v-for="(t, idx) in roomTriplets"
            :key="idx"
            class="triplet"
            :class="{ failed: t.failed }"
          >
            <span class="trip-time">{{ t.time }}</span>
            <span class="trip-s">{{ t.s }}</span>
            <span class="trip-p">{{ t.p }}</span>
            <span class="trip-o">{{ t.o }}</span>
          </div>
        </div>
        <div v-else class="empty">{{ lang.t('（暂无记录）', '(no events yet)') }}</div>
      </div>
    </aside>

    <!-- 三色图例（固定在画布左下） -->
    <div class="legend">
      <div class="lg-row"><span class="lg-dot" style="background:#42A5F5;border-radius:3px"></span>{{ lang.t('房间', 'Room') }}</div>
      <div class="lg-row"><span class="lg-dot" style="background:hsl(30,85%,62%)"></span>{{ lang.t('NPC', 'NPC') }}</div>
      <div class="lg-row"><span class="lg-dot" style="background:#BA68C8;border-radius:2px"></span>{{ lang.t('物品', 'Item') }}</div>
      <div class="lg-row small">{{ lang.t('实线=携带 / 虚线=放置', 'solid=carried / dashed=placed') }}</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue';
import NetworkGraph from '@/components/NetworkGraph.vue';
import { api } from '@/api/endpoints';
import RoomHeatPanel from '@/components/RoomHeatPanel.vue';
import PlaybackControls from '@/components/PlaybackControls.vue';
import Chip from '@/components/Chip.vue';
import { usePlaybackStore } from '@/stores/playback';
import { useWorldStore } from '@/stores/world';
import { useAgentsStore } from '@/stores/agents';
import { useLangStore } from '@/stores/lang';
import { useEventsStore } from '@/stores/events';
import { useHeatStore } from '@/stores/heat';
import type { Room, AgentLite } from '@/api/endpoints';

const lang = useLangStore();
const world = useWorldStore();
const agents = useAgentsStore();
const events = useEventsStore();
const heat = useHeatStore();
const playback = usePlaybackStore();

/* ---- Heatmap toggles (persisted to localStorage) ---- */
const HEAT_LS_KEY = 'sigs_heat_toggles_v1';
const heatLsLoad = (() => {
  try { return JSON.parse(localStorage.getItem(HEAT_LS_KEY) || '{}'); }
  catch { return {}; }
})();
const showMoveHeat = ref<boolean>(heatLsLoad.move ?? true);
const showDwellHeat = ref<boolean>(heatLsLoad.dwell ?? true);
const showHotRoomGlow = ref<boolean>(heatLsLoad.hot ?? true);
watch([showMoveHeat, showDwellHeat, showHotRoomGlow], () => {
  try {
    localStorage.setItem(HEAT_LS_KEY, JSON.stringify({
      move: showMoveHeat.value,
      dwell: showDwellHeat.value,
      hot: showHotRoomGlow.value,
    }));
  } catch {}
});

function clearHeat() {
  if (!confirm(lang.t('清空累计的热力数据？', 'Clear accumulated heat data?'))) return;
  heat.reset();
}

const graphRef = ref<InstanceType<typeof NetworkGraph> | null>(null);
const selectedUid = ref<string | null>(null);
const selectedNpcId = ref<string | null>(null);

/* ---------- NPC inline panel: GOAP plan + chat log ---------- */
const selectedNpcName = computed(() => selectedNpcId.value ? npcNameById(selectedNpcId.value) : '');

// Latest GOAP decision for the selected NPC, pulled from the agent_decision
// events flowing through the events store (also works during playback).
const npcDecision = computed<any | null>(() => {
  const id = selectedNpcId.value;
  if (!id) return null;
  for (let i = events.stream.length - 1; i >= 0; i--) {
    const ev = events.stream[i];
    if (ev?.type === 'agent_decision' && String(ev.agent_id) === id) return ev;
  }
  return null;
});

// Full conversation log for the selected NPC, reconstructed from dialog events
// (the NPC as either speaker or listener), oldest → newest.
interface ChatTurn { key: string; ts: string; mine: string; theirs: string; partner: string; role: 'speaker' | 'listener'; topic: string }
const npcChat = computed<ChatTurn[]>(() => {
  const id = selectedNpcId.value;
  if (!id) return [];
  const en = lang.lang === 'en';
  const out: ChatTurn[] = [];
  // Dedupe: the same dialog line can be re-emitted across ticks. We key on
  // (partner + my line + their line) and keep the latest occurrence, dropping
  // earlier identical turns so the log doesn't fill with repeats.
  const seen = new Map<string, number>();
  for (let i = 0; i < events.stream.length; i++) {
    const ev = events.stream[i];
    if (ev?.type !== 'dialog') continue;
    const p = ev.payload || {};
    const isSpeaker = String(p.speaker_id) === id;
    const isListener = String(p.listener_id) === id;
    if (!isSpeaker && !isListener) continue;
    const sLine = en ? (p.speaker_line_en || p.speaker_line) : (p.speaker_line || p.speaker_line_en);
    const lLine = en ? (p.listener_line_en || p.listener_line) : (p.listener_line || p.listener_line_en);
    const partnerId = isSpeaker ? p.listener_id : p.speaker_id;
    const mine = isSpeaker ? String(sLine || '') : String(lLine || '');
    const theirs = isSpeaker ? String(lLine || '') : String(sLine || '');
    const dedupeKey = `${partnerId}|${mine}|${theirs}`;
    const turn: ChatTurn = {
      key: `${i}-${ev.ts_sim || ''}`,
      ts: hhmm(ev.ts_sim),
      mine,
      theirs,
      partner: npcNameById(String(partnerId || '')),
      role: isSpeaker ? 'speaker' : 'listener',
      topic: en ? (p.topic_en || p.topic || '') : (p.topic || p.topic_en || ''),
    };
    if (seen.has(dedupeKey)) {
      out[seen.get(dedupeKey)!] = turn;  // refresh to latest timestamp, keep order slot
    } else {
      seen.set(dedupeKey, out.length);
      out.push(turn);
    }
  }
  return out;
});
// Activity shown in the GOAP panel: prefer the NPCAgent's persona+scene-aware
// description (activity_desc / _en) over the raw fragment label.
const activityText = computed<string>(() => {
  const p = npcDecision.value?.payload;
  if (!p) return '—';
  const en = lang.lang === 'en';
  const desc = en ? (p.activity_desc_en || p.activity_desc) : (p.activity_desc || p.activity_desc_en);
  return String(desc || p.activity || '—');
});
// True when we're showing a processed description (so we can also surface the
// raw label underneath as a subtle hint).
const activityRaw = computed<string>(() => {
  const p = npcDecision.value?.payload;
  const en = lang.lang === 'en';
  const desc = en ? (p?.activity_desc_en || p?.activity_desc) : (p?.activity_desc || p?.activity_desc_en);
  return desc ? String(p?.activity || '') : '';
});

// Inner-monologue (mutter) feed for the selected NPC, oldest → newest, deduped.
interface MutterTurn { key: string; ts: string; line: string; mood: string }
const npcMutters = computed<MutterTurn[]>(() => {
  const id = selectedNpcId.value;
  if (!id) return [];
  const en = lang.lang === 'en';
  const out: MutterTurn[] = [];
  const seen = new Map<string, number>();
  for (let i = 0; i < events.stream.length; i++) {
    const ev = events.stream[i];
    if (ev?.type !== 'mutter' || String(ev.agent_id) !== id) continue;
    const p = ev.payload || {};
    const line = en ? (p.line_en || p.line) : (p.line || p.line_en);
    if (!line) continue;
    const turn: MutterTurn = {
      key: `${i}-${ev.ts_sim || ''}`,
      ts: hhmm(ev.ts_sim),
      line: String(line),
      mood: String(p.mood || ''),
    };
    const dedupeKey = String(line);
    if (seen.has(dedupeKey)) out[seen.get(dedupeKey)!] = turn;
    else { seen.set(dedupeKey, out.length); out.push(turn); }
  }
  return out;
});
function hhmm(iso: string | undefined): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return String(iso).slice(11, 16);
  return d.toTimeString().slice(0, 5);
}
function closeNpcPanel() { selectedNpcId.value = null; }
function openNpcProfile() {
  if (selectedNpcId.value) window.location.hash = `#/agent/${selectedNpcId.value}`;
}

// ---- NPC tracking state ----
const trackedAgents = ref<string[]>([]);  // ordered list of agent ids
const trackedSet = computed(() => new Set(trackedAgents.value));
const filterText = ref('');
const trackingInitialized = ref(false);  // tracks all NPCs by default on first load

const rooms = computed<Room[]>(() => world.sceneGraph?.rooms || []);
const roomMap = computed<Record<string, Room>>(() => {
  const m: Record<string, Room> = {};
  for (const r of rooms.value) m[r.uid] = r;
  return m;
});
const selected = computed<Room | null>(() => selectedUid.value ? roomMap.value[selectedUid.value] || null : null);

/* Tag-based color palette (lightweight). */
const TAG_COLOR: Record<string, string> = {
  'study':      '#42A5F5',
  'social':     '#66BB6A',
  'leisure':    '#26C6DA',
  'daily life': '#FFA726',
  'fitness':    '#EF5350',
};
function colorOf(tag?: string[]): string {
  if (!tag || !tag.length) return '#90caf9';
  return TAG_COLOR[tag[0]] || '#90caf9';
}

/* ---- View-tuning state (user adjustable, persisted to localStorage) ---- */
const LS_KEY = 'sigs_scene_view_v2';
const lsLoad = (() => {
  try { return JSON.parse(localStorage.getItem(LS_KEY) || '{}'); }
  catch { return {}; }
})();
const roomPosScale = ref<number>(lsLoad.roomPosScale ?? 22);
const roomSize = ref<number>(lsLoad.roomSize ?? 42);
const npcSize = ref<number>(lsLoad.npcSize ?? 7);
const itemSize = ref<number>(lsLoad.itemSize ?? 5);
// Per-move animation duration (ms); larger = slower NPC gliding.
const moveAnimMs = ref<number>(lsLoad.moveAnimMs ?? 2400);
/** World-unit gap between the room hexagon edge and the first NPC satellite
 *  ring. Tunable so users can choose between "NPCs hug the room" (gap=4)
 *  and "NPCs orbit far out" (gap=80) without touching anything else. */
const npcRoomGap = ref<number>(lsLoad.npcRoomGap ?? 16);
const autoScaleOnZoom = ref<boolean>(lsLoad.autoScaleOnZoom ?? true);
const showTunePanel = ref<boolean>(false);
const showHeatPanel = ref<boolean>(false);

/* ---- Inverse-zoom scaling -----------------------------------------
 *  When the user zooms OUT for an overview, individual nodes shrink to
 *  illegibly tiny dots. We compensate by boosting visual node sizes
 *  inversely with the camera scale: `boost = clamp(1, 1/scale, MAX)`.
 *  This keeps the on-screen pixel size of a node roughly CONSTANT as
 *  long as the cap isn't hit (and cushions the shrink below the cap).
 *
 *  Three caps because rooms should dominate the overview while NPC /
 *  item dots should remain peripheral (still visible, but not bigger
 *  than their room). Caps are user-tunable from the ⚙ panel.
 *
 *  IMPORTANT: vis-network's `font.size` is in *screen pixels*, not
 *  world units, so we deliberately do NOT pipe `zoomBoost` into label
 *  sizes — otherwise labels would balloon and visually crowd out the
 *  shapes they're labelling.
 */
const maxRoomBoost = ref<number>(lsLoad.maxRoomBoost ?? 8);
const maxNpcBoost  = ref<number>(lsLoad.maxNpcBoost  ?? 4);
const maxItemBoost = ref<number>(lsLoad.maxItemBoost ?? 4);
const zoomBoost = ref<number>(1);
const roomVisualSize = computed(() => roomSize.value * Math.min(zoomBoost.value, maxRoomBoost.value));
const npcVisualSize  = computed(() => npcSize.value  * Math.min(zoomBoost.value, maxNpcBoost.value));
const itemVisualSize = computed(() => itemSize.value * Math.min(zoomBoost.value, maxItemBoost.value));

function persistView() {
  try {
    localStorage.setItem(LS_KEY, JSON.stringify({
      roomPosScale: roomPosScale.value,
      roomSize: roomSize.value,
      npcSize: npcSize.value,
      itemSize: itemSize.value,
      moveAnimMs: moveAnimMs.value,
      npcRoomGap: npcRoomGap.value,
      autoScaleOnZoom: autoScaleOnZoom.value,
      maxRoomBoost: maxRoomBoost.value,
      maxNpcBoost: maxNpcBoost.value,
      maxItemBoost: maxItemBoost.value,
    }));
  } catch {}
}
watch(
  [roomPosScale, roomSize, npcSize, itemSize, moveAnimMs, npcRoomGap, autoScaleOnZoom,
   maxRoomBoost, maxNpcBoost, maxItemBoost],
  persistView,
);

/* ---- Draggable room positions + background campus map ----
 *  Room nodes can be dragged to any spot; the position is saved server-side
 *  (runtime/scene_layout.json) so it survives a service restart. A campus
 *  map image is drawn behind the graph (in world coordinates) and can be
 *  offset / scaled / faded to align with the rooms. */
const MAP_URL = '/campus_map.png';
// uid → { x, y } in vis-network world units (overrides the computed layout).
const roomPosOverride = reactive<Record<string, { x: number; y: number }>>({});
const mapVisible = ref<boolean>(true);
const mapOpacity = ref<number>(0.55);
const mapScale = ref<number>(1);       // world units per image pixel
const mapX = ref<number>(0);           // world-coord of image center
const mapY = ref<number>(0);
const mapDefaulted = ref<boolean>(false);  // true once we've auto-fit the map once
let layoutLoaded = false;

const mapImage = new Image();
let mapImageReady = false;
mapImage.onload = () => { mapImageReady = true; maybeDefaultMap(); visNet?.redraw?.(); };
mapImage.src = MAP_URL;

/** Effective world-coord center for a room: user override if dragged, else
 *  the template layout (position × spacing). */
function roomCenter(uid: string): { x: number; y: number } {
  const ov = roomPosOverride[uid];
  if (ov) return ov;
  const r = roomMap.value[uid];
  const [rx = 0, ry = 0] = r?.position || [];
  return { x: rx * roomPosScale.value, y: ry * roomPosScale.value };
}

/** Auto-place the map over the room bounding box the first time, when the
 *  user has no saved map transform yet. */
function maybeDefaultMap() {
  if (mapDefaulted.value || !mapImageReady) return;
  const rs = rooms.value;
  if (!rs.length) return;
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  for (const r of rs) {
    const c = roomCenter(r.uid);
    minX = Math.min(minX, c.x); maxX = Math.max(maxX, c.x);
    minY = Math.min(minY, c.y); maxY = Math.max(maxY, c.y);
  }
  if (!isFinite(minX)) return;
  const bw = Math.max(1, maxX - minX);
  const cx = (minX + maxX) / 2;
  const cy = (minY + maxY) / 2;
  mapX.value = cx;
  mapY.value = cy;
  // Fit the image width to ~1.25× the room spread.
  mapScale.value = (bw * 1.25) / (mapImage.naturalWidth || bw);
  mapDefaulted.value = true;
}

let saveTimer: number | null = null;
function persistLayout() {
  if (saveTimer != null) window.clearTimeout(saveTimer);
  saveTimer = window.setTimeout(async () => {
    saveTimer = null;
    try {
      await api.saveSceneLayout({
        rooms: { ...roomPosOverride },
        map: {
          visible: mapVisible.value,
          opacity: mapOpacity.value,
          scale: mapScale.value,
          x: mapX.value,
          y: mapY.value,
          defaulted: mapDefaulted.value,
        },
      });
    } catch (err) {
      console.warn('[scene] save layout failed', err);
    }
  }, 500);
}

async function loadLayout() {
  try {
    const data = await api.sceneLayout();
    const r = data?.rooms || {};
    for (const [uid, pos] of Object.entries(r)) {
      if (pos && typeof (pos as any).x === 'number' && typeof (pos as any).y === 'number') {
        roomPosOverride[uid] = { x: (pos as any).x, y: (pos as any).y };
      }
    }
    const m = data?.map || {};
    if (typeof m.visible === 'boolean') mapVisible.value = m.visible;
    if (typeof m.opacity === 'number') mapOpacity.value = m.opacity;
    if (typeof m.scale === 'number' && m.scale > 0) mapScale.value = m.scale;
    if (typeof m.x === 'number') mapX.value = m.x;
    if (typeof m.y === 'number') mapY.value = m.y;
    if (m.defaulted) mapDefaulted.value = true;
  } catch (err) {
    console.warn('[scene] load layout failed', err);
  } finally {
    layoutLoaded = true;
    maybeDefaultMap();
  }
}

/** Draw the campus map behind the graph, in world coordinates so it pans /
 *  zooms together with the room nodes. */
function drawMap(ctx: CanvasRenderingContext2D) {
  if (!mapVisible.value || !mapImageReady) return;
  const w = mapImage.naturalWidth * mapScale.value;
  const h = mapImage.naturalHeight * mapScale.value;
  ctx.save();
  ctx.globalAlpha = Math.max(0, Math.min(1, mapOpacity.value));
  ctx.drawImage(mapImage, mapX.value - w / 2, mapY.value - h / 2, w, h);
  ctx.restore();
}

// Re-render the canvas + re-save whenever the map transform changes.
watch([mapVisible, mapOpacity, mapScale, mapX, mapY], () => {
  visNet?.redraw?.();
  if (layoutLoaded) persistLayout();
});

/* Slider bounds derived from the room spread so the controls stay usable
 * regardless of the layout's world scale. */
const worldExtent = computed(() => {
  const rs = rooms.value;
  if (!rs.length) return 1000;
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  for (const r of rs) {
    const c = roomCenter(r.uid);
    minX = Math.min(minX, c.x); maxX = Math.max(maxX, c.x);
    minY = Math.min(minY, c.y); maxY = Math.max(maxY, c.y);
  }
  if (!isFinite(minX)) return 1000;
  return Math.max(maxX - minX, maxY - minY, 200);
});
const mapOffsetRange = computed(() => Math.round(worldExtent.value * 2 + 1000));
const mapScaleMin = 0.005;
const mapScaleMax = computed(() => {
  const base = (worldExtent.value * 3) / (mapImage.naturalWidth || 800);
  return Math.max(5, Math.round(base * 100) / 100);
});
const mapScaleStep = 0.005;


/* ---- Current room population (from live world snapshot) ----
 *  The backend snapshot returns `agents` as a dict (keyed by id) while a
 *  few places assume an array — normalise here so we always end up with
 *  `Array<{location_uid?}>`. Falls back to the agents store at startup
 *  before the first world snapshot arrives. */
function snapshotAgentsList(): Array<{ location_uid?: string | null }> {
  const snap = world.worldSnapshot?.agents;
  if (Array.isArray(snap)) return snap;
  if (snap && typeof snap === 'object') return Object.values(snap) as any[];
  return agents.list as any[];
}
const roomPopulation = computed<Record<string, number>>(() => {
  const out: Record<string, number> = {};
  for (const a of snapshotAgentsList()) {
    const uid = a?.location_uid;
    if (uid) out[uid] = (out[uid] || 0) + 1;
  }
  return out;
});
/** UID of the room with the most NPCs *right now*. Null when no agents
 *  are placed yet (very early at startup). */
const hottestCurrentRoom = computed<string | null>(() => {
  let bestUid: string | null = null;
  let bestN = 0;
  for (const [uid, n] of Object.entries(roomPopulation.value)) {
    if (n > bestN) { bestN = n; bestUid = uid; }
  }
  return bestN > 0 ? bestUid : null;
});

/** Heat → CSS color. dwell 0 = base room color, dwell 1 = saturated warm orange.
 *  Mixes the base tag-color with a hot accent in a perceptual way. */
function mixHexWithWarm(hex: string, t: number): string {
  // Clamp t and parse the input hex (#RRGGBB).
  const a = Math.max(0, Math.min(1, t));
  const r1 = parseInt(hex.slice(1, 3), 16);
  const g1 = parseInt(hex.slice(3, 5), 16);
  const b1 = parseInt(hex.slice(5, 7), 16);
  // Hot accent: vivid orange-red (#ff5722).
  const r2 = 0xff, g2 = 0x57, b2 = 0x22;
  const r = Math.round(r1 + (r2 - r1) * a);
  const g = Math.round(g1 + (g2 - g1) * a);
  const b = Math.round(b1 + (b2 - b1) * a);
  return `#${r.toString(16).padStart(2,'0')}${g.toString(16).padStart(2,'0')}${b.toString(16).padStart(2,'0')}`;
}

const vNodes = computed(() =>
  rooms.value.map(r => {
    const baseColor = colorOf(r.tag);
    const dwell = showDwellHeat.value ? heat.dwellHeat(r.uid) : 0;
    // Visually noticeable but never fully blow out the base color.
    const tinted = dwell > 0 ? mixHexWithWarm(baseColor, Math.min(0.8, dwell)) : baseColor;
    const isHot = showHotRoomGlow.value && r.uid === hottestCurrentRoom.value;
    return {
      id: r.uid,
      label: r.name,
      title: `${r.name} · ${r.uid}\n${r.description}`
        + `\n${lang.t('当前 NPC', 'NPCs now')}: ${roomPopulation.value[r.uid] || 0}`
        + `\n${lang.t('累计驻留样本', 'Dwell samples')}: ${heat.dwellRoomCounts[r.uid] || 0}`,
      group: 'room',
      shape: 'hexagon',
      size: roomVisualSize.value,
      color: {
        background: tinted,
        border: isHot ? '#FFD54F' : '#0a0e17',
        highlight: { background: tinted, border: '#FFD54F' },
      },
      borderWidth: isHot ? 4 : 1,
      // vis-network supports a per-node shadow — pulse it on the hot room so
      // the eye finds it instantly without obscuring the rest of the layout.
      shadow: isHot
        ? { enabled: true, color: 'rgba(255,160,0,0.85)', size: 28 * zoomBoost.value, x: 0, y: 0 }
        : (dwell > 0
            ? { enabled: true, color: `rgba(255,87,34,${0.18 + 0.45 * dwell})`, size: (10 + 18 * dwell) * zoomBoost.value, x: 0, y: 0 }
            : { enabled: false }),
      // NOTE: deliberately NO `value` field — vis-network silently switches
      // to value-based scaling (range scaling.min..max, default 10..30) the
      // moment a node carries a `value`, which would override our explicit
      // `size` and pin every hexagon to ~10–30 px regardless of zoom-boost.
      font: {
        color: '#e3f2fd',
        // Font is in *screen pixels* — keep it tied to the BASE roomSize
        // (not the zoom-boosted one), otherwise labels balloon larger
        // than the shapes themselves at low zoom.
        size: Math.max(11, Math.round(roomSize.value * 0.4)),
        strokeWidth: 3,
        strokeColor: '#0a0e17',
      },
      x: roomCenter(r.uid).x,
      y: roomCenter(r.uid).y,
      // Rooms are user-draggable; physics stays off so they don't drift.
      fixed: { x: false, y: false },
      physics: false,
    };
  })
);
const vEdges = computed(() => {
  const seen = new Set<string>();
  const out: any[] = [];
  for (const r of rooms.value) {
    for (const a of (r.adjacent || [])) {
      const key = [r.uid, a].sort().join('|');
      if (seen.has(key)) continue;
      seen.add(key);
      const h = showMoveHeat.value ? heat.moveHeat(r.uid, a) : 0;
      // Width grows from 1.5 (cold) → 7.5 (hottest). Opacity rises with heat too.
      const width = 1.5 + 6 * h;
      const color = h > 0.05
        // Hot edges shift from amber (#ff9800) to red (#ff5722) as heat rises.
        ? (h < 0.5 ? '#ff9800' : '#ff5722')
        : '#37474f';
      const opacity = h > 0 ? Math.min(0.95, 0.55 + 0.4 * h) : 0.75;
      const count = heat.moveEdgeCounts[r.uid < a ? `${r.uid}|${a}` : `${a}|${r.uid}`] || 0;
      out.push({
        from: r.uid, to: a,
        color: { color, opacity },
        width,
        title: count > 0
          ? `${roomLabel(r.uid)} ↔ ${roomLabel(a)} · ${lang.t('累计穿过', 'traversals')} ${count}`
          : `${roomLabel(r.uid)} ↔ ${roomLabel(a)}`,
        smooth: { enabled: false },
      });
    }
  }
  return out;
});

const opts = {
  layout: { improvedLayout: false, randomSeed: 42 },
  nodes: { shape: 'dot', size: 22, font: { size: 13, color: '#cfd8dc' } },
  // Physics disabled everywhere — fully static layout, no idle drifting.
  physics: { enabled: false },
  interaction: { hover: true, tooltipDelay: 80, zoomView: true, dragView: true, dragNodes: true },
};

// ---- NPC tracking: derive nodes + edges to merge into the graph ----
/* Warm-tone NPC palette (saturated oranges/pinks/yellows) so NPCs visually
   pop against the cooler room hexagons. Stable HSL per id. */
function colorForAgent(id: string): string {
  let h = 0;
  for (let i = 0; i < id.length; i++) h = (h * 31 + id.charCodeAt(i)) >>> 0;
  // limit hue to 0-60 (red→yellow) so NPCs read as a "warm" cluster.
  const hue = h % 60;
  return `hsl(${hue}, 85%, 62%)`;
}
const ITEM_COLOR = '#BA68C8';   // purple — distinct from rooms and NPCs

/* ---- NPC pixel-sprite avatars ----
 *  60 sprites sliced from the sheet live at /sprites/npc_00.png … npc_59.png.
 *  Each NPC is assigned a stable sprite by its sorted position in the agent
 *  list (wrapping with modulo if there are ever >60 NPCs). */
const SPRITE_COUNT = 60;
const useSprites = ref<boolean>(lsLoad.useSprites ?? true);
function hashId(id: string): number {
  let h = 0;
  for (let i = 0; i < id.length; i++) h = (h * 31 + id.charCodeAt(i)) >>> 0;
  return h;
}
const spriteIndex = computed<Record<string, number>>(() => {
  const ids = (agents.list || []).map(a => String(a.id)).sort();
  const m: Record<string, number> = {};
  ids.forEach((id, i) => { m[id] = i % SPRITE_COUNT; });
  return m;
});
function spriteUrl(id: string): string {
  const i = spriteIndex.value[id] ?? (hashId(id) % SPRITE_COUNT);
  return `/sprites/npc_${String(i).padStart(2, '0')}.png`;
}
// Pixel sprites read better a few× larger than the old dot size.
const spriteSize = computed(() => npcVisualSize.value * 3.2);

function currentLocation(id: string): string | null {
  const snap = (world.worldSnapshot?.agents) as any;
  if (snap && snap[id]) return snap[id].location_uid || null;
  const a = agents.list.find(x => String(x.id) === id);
  return a ? (a.location_uid || null) : null;
}

/* Stable index of an NPC inside a room (sorted by id) → drives its angle
   on the satellite ring around the room hexagon. */
function npcsInRoom(uid: string): string[] {
  const out: string[] = [];
  for (const id of trackedAgents.value) {
    if (currentLocation(id) === uid) out.push(id);
  }
  return out.sort();
}

/** Returns {x, y} in vis-network world-units for an NPC orbiting its room.
 *  Uses multiple rings (12 NPCs per ring) so dense rooms (35+ NPCs) don't
 *  spill into neighbour rooms. */
function npcSatellitePos(id: string, loc: string): { x: number; y: number } {
  const { x: cx, y: cy } = roomCenter(loc);
  const peers = npcsInRoom(loc);
  const idx = Math.max(0, peers.indexOf(id));
  const PER_RING = 12;
  const ring = Math.floor(idx / PER_RING);
  const slot = idx % PER_RING;
  const slotsThisRing = Math.min(PER_RING, peers.length - ring * PER_RING);
  // Satellite ring radius = (room edge) + npcRoomGap world units.
  // `npcRoomGap` is user-tunable from the ⚙ panel so you can pull NPCs in
  // tight against the room or push them out into a wide orbit. Adding a
  // small NPC-size term keeps a minimum visual gap even when NPCs are
  // boosted larger than the gap.
  // Sprites occupy more space than the old dots — size the orbit to the
  // actual marker size so avatars don't overlap.
  const markerSize = useSprites.value ? spriteSize.value : npcVisualSize.value;
  const minGap = markerSize * 0.9;
  const ringStart = roomVisualSize.value + Math.max(npcRoomGap.value, minGap);
  const ringStep  = markerSize * 1.3 + 3;
  const radius = ringStart + ring * ringStep;
  const angle = (2 * Math.PI * slot) / slotsThisRing - Math.PI / 2;
  return { x: cx + radius * Math.cos(angle), y: cy + radius * Math.sin(angle) };
}

const vNpcNodes = computed(() => {
  const out: any[] = [];
  for (const id of trackedAgents.value) {
    const loc = currentLocation(id);
    if (!loc || !roomMap.value[loc]) continue;
    const a = agents.list.find(x => String(x.id) === id);
    const label = a ? npcName(a) : id;
    const { x, y } = npcSatellitePos(id, loc);
    out.push({
      id: `npc:${id}`,
      label,
      title: `${label}\n@${roomMap.value[loc]?.name || loc}`,
      group: 'npc',
      ...(useSprites.value
        ? {
            shape: 'image',
            image: spriteUrl(id),
            size: spriteSize.value,
            // Crisp nearest-neighbour scaling for pixel art; colored ring on
            // select so the tracker color still reads.
            shapeProperties: { useImageSize: false, interpolation: false },
            color: { border: colorForAgent(id), highlight: { border: '#FFFFFF' } },
          }
        : {
            shape: 'dot',
            size: npcVisualSize.value,
            color: {
              background: colorForAgent(id),
              border: '#1a0d00',
              highlight: { background: colorForAgent(id), border: '#FFFFFF' },
            },
            borderWidth: 1.5,
          }),
      font: {
        color: '#fff',
        size: Math.max(8, Math.round(npcSize.value * 1.0)),
        strokeWidth: 2,
        strokeColor: '#0a0e17',
      },
      x, y,
      fixed: { x: true, y: true },
      physics: false,
    });
  }
  return out;
});
const vNpcEdges = computed(() => {
  const out: any[] = [];
  for (const id of trackedAgents.value) {
    const loc = currentLocation(id);
    if (!loc || !roomMap.value[loc]) continue;
    out.push({
      id: `npc-edge:${id}`,
      from: `npc:${id}`,
      to: loc,
      dashes: [2, 4],
      color: { color: colorForAgent(id), opacity: 0.45 },
      width: 1,
      smooth: { enabled: false },
    });
  }
  return out;
});

/* ---- Items: nodes purple, mounted to either room or NPC ("carrier") ---- */
interface ItemLite { id: string; location_uid?: string; carrier_id?: string | null; extra?: any }
const itemsList = computed<ItemLite[]>(() => {
  const items = (world.worldSnapshot?.items) as Record<string, any> | undefined;
  if (!items) return [];
  return Object.entries(items).map(([id, v]) => ({
    id,
    location_uid: v?.location_uid,
    carrier_id: v?.extra?.carrier_id ?? null,
    extra: v?.extra || {},
  }));
});

function itemDisplayLabel(it: ItemLite): string {
  // strip the trailing index "_3" from "couch_3"
  const name = (it.extra?.name as string) || it.id.replace(/_\d+$/, '');
  return name;
}
function itemSatellitePos(it: ItemLite): { x: number; y: number } | null {
  if (it.carrier_id) {
    // Mount on the NPC: small offset from the NPC node.
    const npcLoc = currentLocation(it.carrier_id);
    if (!npcLoc) return null;
    const p = npcSatellitePos(it.carrier_id, npcLoc);
    const off = (useSprites.value ? spriteSize.value * 0.5 : npcVisualSize.value) + 4;
    return { x: p.x + off, y: p.y - off * 0.4 };
  }
  if (!it.location_uid) return null;
  const room = roomMap.value[it.location_uid];
  if (!room) return null;
  const { x: cx, y: cy } = roomCenter(it.location_uid);
  // Place items on an inner ring close to the room core, evenly spaced.
  const here = itemsList.value.filter(i => !i.carrier_id && i.location_uid === it.location_uid);
  const idx = here.findIndex(i => i.id === it.id);
  const n = Math.max(1, here.length);
  const angle = (2 * Math.PI * idx) / n + Math.PI / 6;
  const r = roomVisualSize.value * 0.7;
  return { x: cx + r * Math.cos(angle), y: cy + r * Math.sin(angle) };
}
const vItemNodes = computed(() => {
  const out: any[] = [];
  for (const it of itemsList.value) {
    const pos = itemSatellitePos(it);
    if (!pos) continue;
    const label = itemDisplayLabel(it);
    const carriedBy = it.carrier_id
      ? (agents.list.find(a => String(a.id) === it.carrier_id) || {} as any).name || it.carrier_id
      : null;
    out.push({
      id: `item:${it.id}`,
      label,
      title: carriedBy
        ? `${label} · 被 ${carriedBy} 携带`
        : `${label} · @${roomMap.value[it.location_uid || '']?.name || it.location_uid}`,
      group: 'item',
      shape: 'square',
      size: itemVisualSize.value,
      color: {
        background: ITEM_COLOR,
        border: it.carrier_id ? '#FFFFFF' : '#4A148C',
        highlight: { background: ITEM_COLOR, border: '#FFFFFF' },
      },
      font: {
        color: '#E1BEE7',
        size: Math.max(7, Math.round(itemSize.value * 1.2)),
        strokeWidth: 2,
        strokeColor: '#0a0e17',
      },
      borderWidth: it.carrier_id ? 2 : 1,
      x: pos.x, y: pos.y,
      fixed: { x: true, y: true },
      physics: false,
    });
  }
  return out;
});
const vItemEdges = computed(() => {
  const out: any[] = [];
  for (const it of itemsList.value) {
    if (it.carrier_id) {
      out.push({
        id: `item-edge:${it.id}`,
        from: `item:${it.id}`,
        to: `npc:${it.carrier_id}`,
        dashes: false,
        color: { color: ITEM_COLOR, opacity: 0.8 },
        width: 1.2,
        smooth: { enabled: false },
      });
    } else if (it.location_uid) {
      out.push({
        id: `item-edge:${it.id}`,
        from: `item:${it.id}`,
        to: it.location_uid,
        dashes: [1, 3],
        color: { color: ITEM_COLOR, opacity: 0.35 },
        width: 0.8,
        smooth: { enabled: false },
      });
    }
  }
  return out;
});

const vNodesAll = computed(() => [...vNodes.value, ...vNpcNodes.value, ...vItemNodes.value]);
const vEdgesAll = computed(() => [...vEdges.value, ...vNpcEdges.value, ...vItemEdges.value]);

const filteredAgents = computed<AgentLite[]>(() => {
  const q = filterText.value.trim().toLowerCase();
  const list = agents.list || [];
  if (!q) return list;
  return list.filter(a => {
    const id = String(a.id).toLowerCase();
    const name = (a.name || '').toLowerCase();
    const ne = ((a as any).name_en || '').toLowerCase();
    return id.includes(q) || name.includes(q) || ne.includes(q);
  });
});

function toggleTrack(id: string) {
  const i = trackedAgents.value.indexOf(id);
  if (i >= 0) trackedAgents.value.splice(i, 1);
  else trackedAgents.value.push(id);
}
function trackAll() {
  trackedAgents.value = (agents.list || []).map(a => String(a.id));
}
function trackNone() { trackedAgents.value = []; }

function shortTime(iso: string): string {
  // 2026-05-26T07:35:00 → 05-26 07:35
  try {
    return iso.replace('T', ' ').slice(5, 16);
  } catch {
    return iso;
  }
}

function onSelectNode(nodeId: string) {
  // virtual NPC nodes start with "npc:" — clicking one opens the inline NPC
  // panel (GOAP plan + chat log) instead of navigating away.
  if (nodeId.startsWith('npc:')) {
    const aid = nodeId.slice(4);
    (window as any).__lastClickedAgent = aid;
    selectedNpcId.value = aid;
    const st = (world.worldSnapshot?.agents || []).find((a: any) => String(a.id) === aid)
      || agents.list.find(a => String(a.id) === aid);
    if (st?.location_uid) selectedUid.value = st.location_uid;
    return;
  }
  // virtual item nodes select their carrier's room.
  if (nodeId.startsWith('item:')) {
    const iid = nodeId.slice(5);
    const it = itemsList.value.find(x => x.id === iid);
    if (it?.location_uid) selectedUid.value = it.location_uid;
    return;
  }
  selectedUid.value = nodeId;
}
function jumpToRoom(uid: string) {
  selectedUid.value = uid;
  graphRef.value?.focus?.(uid);
}
function resetView() {
  graphRef.value?.fit?.();
}
function resetSizes() {
  roomPosScale.value = 22;
  roomSize.value = 42;
  npcSize.value = 7;
  itemSize.value = 5;
  moveAnimMs.value = 2400;
}
function roomLabel(uid: string | null | undefined): string {
  if (!uid) return '—';
  return roomMap.value[uid]?.name || uid;
}

const agentsHere = computed<AgentLite[]>(() => {
  const uid = selectedUid.value;
  if (!uid) return [];
  // Prefer the world snapshot if loaded; fall back to agents.list.
  const snap = (world.worldSnapshot?.agents || []) as any[];
  const here = snap.length
    ? snap.filter(a => a.location_uid === uid)
    : agents.list.filter(a => a.location_uid === uid);
  // Hydrate names from agents.list by id when needed.
  return here.map(a => ({
    ...(agents.list.find(b => String(b.id) === String(a.id)) || {}),
    ...a,
  })) as AgentLite[];
});
function npcName(a: AgentLite): string {
  if (lang.lang === 'en') return (a as any).name_en || a.name || String(a.id);
  return a.name || (a as any).name_en || String(a.id);
}
function npcNameById(id: string): string {
  const a = agents.list.find(x => String(x.id) === id);
  return a ? npcName(a) : id;
}

/* ---------- Items panel: items currently in the selected room ---------- */
const itemsHere = computed<ItemLite[]>(() => {
  const uid = selectedUid.value;
  if (!uid) return [];
  return itemsList.value.filter(it => it.location_uid === uid);
});

/* ---------- Room triplet event stream (S, P, O) ---------- */
interface Triplet { time: string; s: string; p: string; o: string; failed?: boolean }
const ACTION_LABEL_ZH: Record<string, string> = {
  move: '走到', talk: '与…交谈', interact: '使用', sleep: '入睡',
  wake_up: '醒来', idle: '休息', pickup: '拾起', drop: '放下',
};
const ACTION_LABEL_EN: Record<string, string> = {
  move: 'walks to', talk: 'talks with', interact: 'uses', sleep: 'sleeps',
  wake_up: 'wakes up', idle: 'idles', pickup: 'picks up', drop: 'drops',
};
function predicateFor(action: string): string {
  return lang.lang === 'en'
    ? (ACTION_LABEL_EN[action] || action)
    : (ACTION_LABEL_ZH[action] || action);
}
function shortHHMM(ts?: string): string {
  if (!ts) return '';
  // 2026-05-26T07:35:00 → 07:35
  return ts.includes('T') ? ts.split('T')[1].slice(0, 5) : ts.slice(0, 5);
}
const roomTriplets = computed<Triplet[]>(() => {
  const uid = selectedUid.value;
  if (!uid) return [];
  const out: Triplet[] = [];
  // walk newest → oldest, take up to 25
  for (let i = events.stream.length - 1; i >= 0 && out.length < 25; i--) {
    const ev = events.stream[i];
    const p = ev.payload || {};
    if (ev.type === 'dialog' && p.here_uid === uid) {
      const sName = lang.lang === 'en' ? (p.speaker_name_en || p.speaker_name) : (p.speaker_name || p.speaker_name_en);
      const lName = lang.lang === 'en' ? (p.listener_name_en || p.listener_name) : (p.listener_name || p.listener_name_en);
      out.push({
        time: shortHHMM(ev.ts_sim),
        s: sName || p.speaker_id,
        p: predicateFor('talk'),
        o: lName || p.listener_id,
      });
    } else if (ev.type === 'behavior') {
      const preLoc = p.pre_state?.['agent.location_uid'];
      const postLoc = p.post_state?.['agent.location_uid'];
      if (preLoc !== uid && postLoc !== uid) continue;
      const action = p.action_id || 'act';
      const npc = npcNameById(String(ev.agent_id || ''));
      let obj = '';
      if (action === 'move') {
        obj = roomLabel(postLoc) + (preLoc && preLoc !== postLoc ? `  (← ${roomLabel(preLoc)})` : '');
      } else if (action === 'pickup' || action === 'drop') {
        const iid = p.params?.item_id || p.item_id || '';
        const it = itemsList.value.find(x => x.id === iid);
        obj = it ? itemDisplayLabel(it) : (iid || (p.activity || ''));
      } else {
        obj = p.activity || roomLabel(postLoc || preLoc);
      }
      out.push({
        time: shortHHMM(ev.ts_sim),
        s: npc,
        p: predicateFor(action),
        o: obj,
        failed: !p.ok,
      });
    }
  }
  return out;
});

/* ====================================================================
   NPC MOVE ANIMATION
   --------------------------------------------------------------------
   When the backend publishes a `behavior` event with `action_id="move"`,
   we lerp the NPC node from its old room's satellite slot to a slot on
   the new room over ~1.2s. After the lerp finishes, the next world
   snapshot poll will reaffirm the final position (no visual jump because
   the lerp's endpoint matches the satellite slot we computed).
   ==================================================================== */
/** Tracks the last `events.pushedTotal` value we've processed for heat /
 *  animation. Using a monotonic counter (rather than a stream index) is
 *  necessary because the events stream is a ring buffer — indices shift
 *  once it saturates, so `stream.length` alone can't detect new pushes. */
let lastSeenPushedTotal = 0;
const animations = new Map<string, number>();    // npc id → raf handle

/* ---- Speech bubbles above NPC sprites ----
 *  On a `dialog` event we float the spoken line above the speaker (and the
 *  reply above the listener). Positions are recomputed each animation frame
 *  from the node's world coords → screen coords so bubbles track panning,
 *  zooming, dragging and NPC movement. */
type BubbleKind = 'dialog' | 'thought';
interface Bubble { key: number; agentId: string; until: number; x: number; y: number; show: boolean; kind: BubbleKind }
const bubbles = ref<Bubble[]>([]);
let bubbleKey = 0;
let bubbleRaf: number | null = null;
const BUBBLE_MS = 4500;

// Show a "talking" (dialog) or "thinking" (mutter) indicator over an NPC. If
// one is already active, extend it instead of stacking (one bubble per NPC).
function addBubble(agentId: string, kind: BubbleKind = 'dialog') {
  if (!agentId) return;
  const existing = bubbles.value.find(b => b.agentId === agentId);
  if (existing) {
    existing.until = performance.now() + BUBBLE_MS;
    existing.kind = kind;
    ensureBubbleLoop();
    return;
  }
  bubbles.value.push({
    key: ++bubbleKey,
    agentId,
    until: performance.now() + BUBBLE_MS,
    x: -9999, y: -9999, show: false,
    kind,
  });
  ensureBubbleLoop();
}
function ensureBubbleLoop() {
  if (bubbleRaf == null) bubbleRaf = requestAnimationFrame(updateBubbles);
}
function updateBubbles() {
  const now = performance.now();
  bubbles.value = bubbles.value.filter(b => b.until > now);
  if (visNet && bubbles.value.length) {
    const scale = (visNet.getScale?.() as number) || 1;
    for (const b of bubbles.value) {
      const nid = `npc:${b.agentId}`;
      const pos = visNet.getPositions?.([nid])?.[nid];
      if (pos) {
        const dom = visNet.canvasToDOM({ x: pos.x, y: pos.y });
        b.x = dom.x;
        // Sit the bubble's tail just above the sprite's head.
        b.y = dom.y - (spriteSize.value * scale * 0.6 + 12);
        b.show = true;
      } else {
        b.show = false;
      }
    }
  }
  bubbleRaf = bubbles.value.length ? requestAnimationFrame(updateBubbles) : null;
}

/* ---- Zoom event → inverse-boost factor ----
 *  vis-network fires `zoom` on every wheel tick. We collapse those into
 *  one update per animation frame and tween nothing — Vue's reactivity
 *  picks up the new `zoomBoost` and the dependent size computeds
 *  re-emit fresh nodes for vis-network to render. */
let zoomRaf: number | null = null;
let visNet: any = null;
function onNetReady(net: any) {
  visNet = net;
  net.on('zoom', () => scheduleZoomBoostUpdate());
  // Also re-evaluate after fit/move animations finish, because vis-network
  // doesn't always emit `zoom` during fit() / moveTo() animations.
  net.on('animationFinished', () => scheduleZoomBoostUpdate());
  net.on('dragEnd', (params: any) => {
    handleDragEnd(params);
    scheduleZoomBoostUpdate();
  });
  // Draw the campus map behind every frame (world coords → pans/zooms too).
  net.on('beforeDrawing', (ctx: CanvasRenderingContext2D) => drawMap(ctx));
  // Initial sync (fit() during mount may set scale before our listener attaches).
  scheduleZoomBoostUpdate();
  net.redraw?.();
}

/** Persist final positions of any dragged ROOM nodes (npc:/item: nodes are
 *  satellites and not user-draggable). */
function handleDragEnd(params: any) {
  const ids: string[] = (params?.nodes || []).map((x: any) => String(x));
  const roomIds = ids.filter(id => !id.startsWith('npc:') && !id.startsWith('item:') && roomMap.value[id]);
  if (!roomIds.length || !visNet) return;
  const positions = visNet.getPositions(roomIds);
  let changed = false;
  for (const uid of roomIds) {
    const p = positions[uid];
    if (p) { roomPosOverride[uid] = { x: Math.round(p.x), y: Math.round(p.y) }; changed = true; }
  }
  if (changed) persistLayout();
}

/** Clear all dragged room positions → revert to template layout. */
function resetRoomPositions() {
  for (const k of Object.keys(roomPosOverride)) delete roomPosOverride[k];
  persistLayout();
}
function scheduleZoomBoostUpdate() {
  if (!autoScaleOnZoom.value) {
    if (zoomBoost.value !== 1) zoomBoost.value = 1;
    return;
  }
  if (zoomRaf != null) return;
  zoomRaf = requestAnimationFrame(() => {
    zoomRaf = null;
    if (!visNet) return;
    const scale = (visNet.getScale?.() as number) || 1;
    // No boost when zoomed in past parity; otherwise boost = 1/scale.
    // Per-type caps (maxRoomBoost / maxNpcBoost / maxItemBoost) are
    // applied at consumption time, so a huge boost here just means each
    // node type rides up to its own ceiling.
    const ABSOLUTE_CAP = 16;  // sanity-bound for scale → 0 edge cases
    const target = scale >= 1 ? 1 : Math.min(ABSOLUTE_CAP, 1 / scale);
    // Round to 2 decimals so tiny scale jitters (e.g. animations) don't
    // trigger a re-render every frame.
    const rounded = Math.round(target * 100) / 100;
    if (Math.abs(rounded - zoomBoost.value) > 0.005) {
      zoomBoost.value = rounded;
    }
  });
}
// Re-evaluate boost (forced to 1) the moment the user toggles auto-scale off.
watch(autoScaleOnZoom, scheduleZoomBoostUpdate);

function animateNpcMove(id: string, fromUid: string, toUid: string) {
  const net = graphRef.value as any;
  if (!net?.updateNodes) return;
  // Compute endpoints in the same coord-space as everything else.
  const fromRoom = roomMap.value[fromUid];
  const toRoom = roomMap.value[toUid];
  if (!fromRoom || !toRoom) return;
  const fromPos = npcSatellitePos(id, fromUid);
  // For the target slot, anticipate the post-move ring (peers ≈ npcsInRoom(toUid)).
  // Approximation is good enough because the next snapshot recompute corrects it.
  const toPos = npcSatellitePos(id, toUid);

  const start = performance.now();
  // Cancel any in-flight animation for this NPC.
  if (animations.has(id)) {
    cancelAnimationFrame(animations.get(id)!);
    animations.delete(id);
  }
  const dur = Math.max(200, moveAnimMs.value);
  const tick = (now: number) => {
    const t = Math.min(1, (now - start) / dur);
    // Ease in/out cubic.
    const e = t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
    const x = fromPos.x + (toPos.x - fromPos.x) * e;
    const y = fromPos.y + (toPos.y - fromPos.y) * e;
    const updates: any[] = [{ id: `npc:${id}`, x, y }];
    // If this NPC is carrying an item, drag it along too.
    for (const it of itemsList.value) {
      if (it.carrier_id === id) {
        updates.push({ id: `item:${it.id}`, x: x + 22, y: y - 8 });
      }
    }
    net.updateNodes(updates);
    if (t < 1) {
      animations.set(id, requestAnimationFrame(tick));
    } else {
      animations.delete(id);
    }
  };
  animations.set(id, requestAnimationFrame(tick));
}

/** Process a single sim event into heat / animations. Idempotent guard
 *  rails live in the move/animate handlers themselves. The `animate`
 *  arg lets us run animations only for NEW events (skip backfill). */
function processSimEvent(ev: any, animate: boolean) {
  // Dialog → speech bubbles over speaker + listener (only for new/live events,
  // not historical backfill).
  if (ev?.type === 'dialog' && animate) {
    const p = ev.payload || {};
    if (p.speaker_id) addBubble(String(p.speaker_id));
    if (p.listener_id) addBubble(String(p.listener_id));
    return;
  }
  // Mutter (inner monologue) → a "thinking" bubble over the NPC.
  if (ev?.type === 'mutter' && animate) {
    const p = ev.payload || {};
    if (p.agent_id) addBubble(String(p.agent_id), 'thought');
    return;
  }
  if (ev?.type !== 'behavior') return;
  const p = ev.payload || {};
  if (p.action_id !== 'move' || !p.ok) return;
  const aid = String(ev.agent_id || '');
  const from = p.pre_state?.['agent.location_uid'];
  const to = p.post_state?.['agent.location_uid'];
  if (!aid || !from || !to || from === to) return;
  // Heat-map: record every successful traversal regardless of tracking.
  heat.recordMove(String(from), String(to));
  if (animate && trackedSet.value.has(aid)) {
    animateNpcMove(aid, String(from), String(to));
  }
}

watch(
  () => events.pushedTotal,
  (total) => {
    const newCount = total - lastSeenPushedTotal;
    if (newCount <= 0) { lastSeenPushedTotal = total; return; }
    // Only the most recent `newCount` events are guaranteed to be the
    // newcomers; older indices may have just been evicted by the ring
    // buffer. Clamp to stream length so we don't underflow.
    const start = Math.max(0, events.stream.length - newCount);
    for (let i = start; i < events.stream.length; i++) {
      processSimEvent(events.stream[i], /*animate=*/true);
    }
    lastSeenPushedTotal = total;
  },
);

/* Sample dwell heat whenever a new world snapshot is observed. The
 * snapshot's `sim_time` field is the dedupe key (it's stamped server-side
 * once per simulation tick), so both REST polling and WS pushes feed the
 * same accumulator without double-counting. */
watch(
  () => world.worldSnapshot?.sim_time ?? world.lastTickAt,
  (tickAt) => {
    if (!tickAt) return;
    heat.sampleDwell(String(tickAt), snapshotAgentsList());
  },
);

onMounted(async () => {
  await Promise.all([
    world.loadScene(),
    world.loadWorld(),
    agents.loadList(),
  ]);
  // Load saved room positions + map transform (after rooms so we can
  // auto-fit the map on first run).
  await loadLayout();
  // Backfill heat counters from any events already in the ring buffer
  // (e.g. user switched here from another tab). We DON'T animate these —
  // they're history — but we do count them for the move-route heat map.
  for (const ev of events.stream) processSimEvent(ev, /*animate=*/false);
  lastSeenPushedTotal = events.pushedTotal;
  // Track every NPC by default so the user immediately sees motion.
  if (!trackingInitialized.value && agents.list?.length) {
    trackedAgents.value = agents.list.map(a => String(a.id));
    trackingInitialized.value = true;
  }
  // Poll world snapshot every 3s so tracked NPC nodes / items re-attach when
  // they change room. Animations (1.2s) finish before the next poll lands.
  // (Suppressed while a recording is being played back.)
  if (!playback.active) world.startPolling(3000);
  // Center the camera on the room centroid at a useful zoom.
  setTimeout(() => {
    const rs = rooms.value;
    if (!rs.length) return;
    let sx = 0, sy = 0;
    for (const r of rs) {
      sx += (r.position?.[0] || 0) * roomPosScale.value;
      sy += (r.position?.[1] || 0) * roomPosScale.value;
    }
    const cx = sx / rs.length;
    const cy = sy / rs.length;
    (graphRef.value as any)?.moveTo?.({
      position: { x: cx, y: cy },
      scale: 0.5,
      animation: false,
    });
  }, 150);
});
// While playback owns the world, stop live polling; resume on exit.
watch(() => playback.active, (on) => {
  if (on) world.stopPolling();
  else world.startPolling(3000);
});

onBeforeUnmount(() => {
  for (const h of animations.values()) cancelAnimationFrame(h);
  animations.clear();
  if (bubbleRaf != null) cancelAnimationFrame(bubbleRaf);
  world.stopPolling();
  // Hand the world back to the live feed if we leave mid-playback.
  if (playback.active) playback.exit();
});
</script>

<style scoped>
.scene-page { display: flex; height: 100%; }
.scene-graph { flex: 1; position: relative; min-width: 0; }

/* ---- Speech bubbles ---- */
.bubble-layer {
  position: absolute; inset: 0;
  pointer-events: none;
  overflow: hidden;
  z-index: 6;
}
.bubble {
  position: absolute;
  transform: translate(-50%, -100%);
  background: rgba(255,255,255,0.96);
  border-radius: 11px;
  padding: 5px 9px;
  box-shadow: 0 3px 10px rgba(0,0,0,0.45);
}
.bubble::after {
  content: '';
  position: absolute;
  bottom: -6px; left: 50%; transform: translateX(-50%);
  border-left: 6px solid transparent;
  border-right: 6px solid transparent;
  border-top: 7px solid rgba(255,255,255,0.96);
}
.bubble-dots { display: flex; gap: 3px; align-items: center; }
.bubble-dots i {
  width: 4px; height: 4px; border-radius: 50%;
  background: #5b6b86;
  animation: bubble-blink 1.2s infinite ease-in-out;
}
.bubble-dots i:nth-child(2) { animation-delay: 0.2s; }
.bubble-dots i:nth-child(3) { animation-delay: 0.4s; }
@keyframes bubble-blink {
  0%, 80%, 100% { opacity: 0.25; transform: translateY(0); }
  40% { opacity: 1; transform: translateY(-2px); }
}
/* Mutter (inner monologue) bubble — softer, with a thought glyph. */
.bubble--thought { background: rgba(226,236,255,0.96); }
.bubble--thought::after { border-top-color: rgba(226,236,255,0.96); }
.bubble-think { font-size: 12px; line-height: 1; display: block; }
/* ---- NPC inline panel (GOAP plan + chat log) ---- */
.npc-panel {
  border: 1px solid var(--border, #2a3550);
  border-radius: 10px;
  padding: 10px 12px 12px;
  margin-bottom: 12px;
  background: rgba(255,255,255,0.03);
}
.npc-panel-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.npc-panel-title { display: flex; align-items: center; gap: 6px; font-weight: 700; font-size: 14px; }
.npc-panel-title .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--accent-active, #4ea1ff); }
.npc-panel-actions { display: flex; gap: 6px; }
.mini-btn {
  font-size: 11px; padding: 2px 8px; border-radius: 6px; cursor: pointer;
  border: 1px solid var(--border, #2a3550); background: transparent; color: inherit;
}
.mini-btn:hover { background: rgba(255,255,255,0.08); }
.goap-box { font-size: 12px; }
.goap-row { display: flex; gap: 8px; margin: 3px 0; }
.goap-k { flex: 0 0 64px; color: var(--text-dim, #8aa); }
.goap-v { flex: 1; word-break: break-word; }
.goap-kind { color: var(--text-dim, #8aa); font-style: normal; font-size: 10px; margin-left: 4px; }
.goap-raw { display: block; color: var(--text-dim, #8aa); font-size: 10px; margin-top: 2px; opacity: 0.8; }
.goal-chip {
  display: inline-block; padding: 1px 6px; margin: 0 4px 4px 0;
  border-radius: 5px; background: rgba(78,161,255,0.15); border: 1px solid rgba(78,161,255,0.4);
}
.goap-arrow { text-align: center; color: var(--text-dim, #8aa); font-size: 11px; margin: 6px 0 4px; }
.chain { display: flex; flex-direction: column; gap: 4px; }
.chain-step {
  display: flex; align-items: center; gap: 8px;
  padding: 4px 8px; border-radius: 6px;
  background: rgba(255,255,255,0.04); border: 1px solid var(--border, #2a3550);
}
.chain-step.active { border-color: var(--accent-active, #4ea1ff); background: rgba(78,161,255,0.12); }
.chain-idx {
  flex: 0 0 18px; height: 18px; line-height: 18px; text-align: center;
  border-radius: 50%; background: rgba(255,255,255,0.1); font-size: 10px;
}
.chain-label { flex: 1; }
.chain-cost { color: var(--text-dim, #8aa); font-size: 10px; }
.goap-exec { margin-top: 6px; font-size: 11px; color: var(--text-dim, #9bb); }
.goap-exec .mono { margin-left: 4px; }
.chatlog { display: flex; flex-direction: column; gap: 8px; max-height: 320px; overflow-y: auto; }
.chat-turn { border-left: 2px solid rgba(78,161,255,0.4); padding-left: 8px; }
.chat-meta { display: flex; gap: 8px; font-size: 10px; color: var(--text-dim, #8aa); margin-bottom: 2px; }
.chat-topic { font-style: italic; }
.chat-line { font-size: 12px; line-height: 1.35; margin: 1px 0; word-break: break-word; }
.chat-line.theirs { color: var(--text-dim, #aab); }
.mutterlog { display: flex; flex-direction: column; gap: 6px; max-height: 220px; overflow-y: auto; }
.mutter-turn {
  display: flex; align-items: baseline; gap: 6px;
  border-left: 2px solid rgba(170,150,255,0.45); padding-left: 8px;
  font-size: 12px; line-height: 1.35;
}
.mutter-time { flex: 0 0 auto; font-size: 10px; color: var(--text-dim, #8aa); }
.mutter-line { flex: 1; font-style: italic; color: var(--text-dim, #c2bdf0); word-break: break-word; }
.mutter-mood {
  flex: 0 0 auto; font-size: 10px; color: #b8a8ff;
  border: 1px solid rgba(170,150,255,0.4); border-radius: 5px; padding: 0 5px;
}
.scene-side {
  width: 380px;
  background: var(--bg-panel);
  border-left: 1px solid var(--border-soft);
  display: flex;
  flex-direction: column;
  overflow-y: auto;
}
.scene-side > .rhp {
  border-bottom: 1px solid var(--border-soft);
  background: var(--bg-elevated);
}

.stats {
  position: absolute;
  top: 16px; left: 16px;
  background: rgba(18,24,43,0.92);
  border: 1px solid var(--border-soft);
  padding: 8px 14px;
  font-size: 12px;
  color: var(--text-very-dim);
  border-radius: 12px;
  display: flex; gap: 14px;
}
.stats b { color: var(--accent-warn); margin-left: 4px; }

.topright { position: absolute; top: 16px; right: 16px; }
.topright-actions {
  position: absolute;
  top: 16px; right: 16px;
  display: flex; gap: 8px;
  z-index: 6;
}

/* ---- Heat-map control panel ---- */
.heat-panel {
  position: absolute;
  top: 62px;
  right: 16px;
  width: 280px;
  background: rgba(18,24,43,0.96);
  border: 1px solid var(--border-soft);
  border-radius: 10px;
  padding: 10px 12px;
  box-shadow: 0 6px 20px rgba(0,0,0,0.45);
  z-index: 6;
  color: var(--text-secondary);
  font-size: 12px;
}
.heat-header {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 8px;
}
.heat-header strong { color: var(--accent-warn); font-size: 13px; }
.heat-row {
  display: flex; align-items: center; gap: 8px;
  font-size: 12px;
  color: var(--text-secondary);
  cursor: pointer;
  padding: 3px 0;
}
.heat-row input[type="checkbox"] { accent-color: var(--accent-warn); cursor: pointer; }
.heat-sw {
  display: inline-block;
  width: 16px; height: 4px;
  border-radius: 2px;
}
.heat-sw.move  { background: linear-gradient(90deg, #ff9800, #ff5722); }
.heat-sw.dwell { background: radial-gradient(circle, #ff5722 0%, transparent 70%); height: 8px; width: 8px; border-radius: 50%; }
.heat-sw.glow  { background: #FFD54F; box-shadow: 0 0 6px rgba(255,213,79,0.9); }
.heat-num {
  color: var(--text-very-dim);
  font-family: Consolas, monospace;
  font-size: 10.5px;
  margin-left: auto;
}
.heat-hot-now {
  margin-top: 8px;
  padding: 5px 8px;
  background: rgba(255,213,79,0.08);
  border-left: 2px solid var(--accent-warn);
  border-radius: 4px;
  font-size: 11.5px;
  color: var(--text-secondary);
}
.heat-hot-now b { color: var(--accent-warn); margin: 0 4px; }
.heat-hint {
  margin-top: 8px;
  font-size: 10.5px;
  line-height: 1.5;
  color: var(--text-very-dim);
  font-style: italic;
}

/* ---- View tuning panel ---- */
.tune-panel {
  position: absolute;
  top: 62px;
  right: 16px;
  width: 260px;
  background: rgba(18,24,43,0.96);
  border: 1px solid var(--border-soft);
  border-radius: 10px;
  padding: 10px 12px;
  box-shadow: 0 6px 20px rgba(0,0,0,0.45);
  z-index: 6;
  color: var(--text-secondary);
  font-size: 12px;
  transition: top 0.18s ease;
}
/* When the heat-panel is also visible, slide tune-panel below it instead
 * of overlapping. (Height of heat-panel ≈ 245px + 16px gap.) */
.tune-panel.shift-below-heat { top: 320px; }
.tune-header {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 8px;
}
.tune-header strong { color: var(--accent-primary); font-size: 13px; }
.tune-row {
  display: grid;
  grid-template-columns: 90px 1fr 32px;
  align-items: center;
  gap: 6px;
  margin: 4px 0;
}
.tune-row label { color: var(--text-very-dim); }
.tune-row input[type=range] { width: 100%; }
.tune-row.sub {
  margin-left: 14px;
  opacity: 0.85;
  border-left: 2px solid var(--border-soft);
  padding-left: 8px;
}
.tune-val {
  text-align: right;
  font-family: Consolas, monospace;
  color: var(--accent-warm-soft);
  font-size: 11px;
}
.tune-toggle {
  display: flex; align-items: center; gap: 8px;
  margin: 8px 0 2px;
  font-size: 12px;
  color: var(--text-secondary);
  cursor: pointer;
  padding-top: 6px;
  border-top: 1px dashed var(--border-soft);
}
.tune-toggle input[type=checkbox] { accent-color: var(--accent-warn); cursor: pointer; }
.tune-toggle .tune-val { margin-left: auto; }
.tune-hint {
  margin-top: 6px;
  font-size: 10.5px;
  color: var(--text-very-dim);
  font-style: italic;
}
.tune-divider {
  margin: 10px 0 4px;
  padding-top: 8px;
  border-top: 1px dashed var(--border-soft);
  color: var(--accent-warm-soft);
  font-size: 11.5px;
  font-weight: 600;
}
.tune-toggle.no-border { border-top: none; padding-top: 2px; margin-top: 2px; }
.micro-btn.full {
  width: 100%;
  margin-top: 8px;
  padding: 5px 8px;
}

.panel-header {
  padding: 14px 18px;
  background: var(--bg-elevated);
  border-bottom: 1px solid var(--border-soft);
}
.panel-header h2 { font-size: 16px; color: var(--accent-primary); }
.panel-content { padding: 14px 18px; flex: 1; overflow-y: auto; }
.placeholder {
  color: var(--text-disabled);
  text-align: center;
  padding: 30px 8px;
}

.room-name {
  color: var(--accent-warm-soft);
  font-size: 18px;
  font-weight: 700;
  margin-bottom: 8px;
}
.kv { display: flex; gap: 6px; font-size: 12.5px; color: var(--text-secondary); margin: 3px 0; }
.kv .k { color: var(--text-very-dim); min-width: 70px; }
.kv .v { color: var(--text-secondary); }
.kv-block { background: var(--bg-card); padding: 6px 10px; border-radius: 6px; margin-top: 4px; }
.mono { font-family: Consolas, monospace; font-size: 11px; }
.desc {
  background: var(--bg-card);
  padding: 8px 10px;
  border-radius: 6px;
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.6;
}
.empty { color: var(--text-disabled); font-size: 12px; padding: 4px 0; }

/* ---- NPC tracker panel ---- */
.tracker-panel {
  position: absolute;
  bottom: 16px; left: 16px;
  width: 280px;
  max-height: 50vh;
  display: flex; flex-direction: column;
  background: rgba(18,24,43,0.94);
  border: 1px solid var(--border-soft);
  border-radius: 12px;
  padding: 10px 12px;
  box-shadow: 0 6px 20px rgba(0,0,0,0.35);
  z-index: 5;
}
.tracker-header {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 8px;
}
.tracker-header strong { color: var(--accent-primary); font-size: 13px; }
.tracker-actions { display: flex; gap: 6px; }
.micro-btn {
  background: var(--bg-card);
  border: 1px solid var(--border-soft);
  color: var(--text-secondary);
  font-size: 11px;
  padding: 3px 8px;
  border-radius: 6px;
  cursor: pointer;
}
.micro-btn:hover { background: var(--bg-elevated); color: var(--accent-primary); }
.tracker-filter {
  width: 100%;
  background: var(--bg-card);
  border: 1px solid var(--border-soft);
  color: var(--text-primary);
  font-size: 12px;
  padding: 4px 8px;
  border-radius: 6px;
  margin-bottom: 6px;
  outline: none;
  box-sizing: border-box;
}
.tracker-list { overflow-y: auto; max-height: 30vh; }
.tracker-item {
  display: flex; align-items: center; gap: 6px;
  padding: 3px 0;
  font-size: 12px;
  color: var(--text-secondary);
  cursor: pointer;
}
.tracker-item:hover { color: var(--text-primary); }
.tracker-item .dot {
  width: 10px; height: 10px; border-radius: 50%;
  display: inline-block;
}
.tracker-name { flex: 1; }
.tracker-loc { color: var(--text-very-dim); font-size: 10.5px; }
.sim-clock { color: var(--accent-warm-soft); margin-left: auto; }
.empty-small { color: var(--text-disabled); font-size: 11px; padding: 4px; text-align: center; }

/* ---- Triplet panel (events in selected room) ---- */
.triplet-list { display: flex; flex-direction: column; gap: 4px; margin-top: 4px; }
.triplet {
  display: grid;
  grid-template-columns: 38px 1fr auto 1fr;
  gap: 6px;
  align-items: center;
  background: var(--bg-card);
  border: 1px solid var(--border-soft);
  border-left: 3px solid #66BB6A;
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 11.5px;
  color: var(--text-secondary);
}
.triplet.failed { border-left-color: #EF5350; opacity: 0.8; }
.triplet .trip-time { color: var(--text-very-dim); font-family: Consolas, monospace; font-size: 10.5px; }
.triplet .trip-s { color: #FFD54F; font-weight: 600; }
.triplet .trip-p {
  color: var(--text-disabled);
  background: rgba(255,255,255,0.04);
  padding: 1px 6px;
  border-radius: 8px;
  font-size: 10.5px;
}
.triplet .trip-o { color: #81D4FA; }

/* ---- Legend ---- */
.legend {
  position: absolute;
  bottom: 16px; right: 16px;
  background: rgba(18,24,43,0.94);
  border: 1px solid var(--border-soft);
  border-radius: 10px;
  padding: 8px 12px;
  font-size: 11.5px;
  color: var(--text-secondary);
  z-index: 5;
  display: flex; flex-direction: column; gap: 4px;
}
.lg-row { display: flex; align-items: center; gap: 6px; }
.lg-row.small { color: var(--text-very-dim); font-size: 10.5px; margin-top: 2px; }
.lg-dot { width: 12px; height: 12px; border-radius: 50%; display: inline-block; }
</style>
