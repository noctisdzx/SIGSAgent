/**
 * Inline mock data — kept tiny.
 * Used as a fallback when the backend is offline so visual iteration on the
 * frontend remains possible. Stores import these via `mockOnFail()`.
 */

import type { AgentLite, RelationEdge, SceneEntry, TimelineEvent, Room } from '@/api/endpoints';

export const MOCK_AGENTS: AgentLite[] = [
  // Literature
  { id: 1, name: '林晓薇', name_en: 'Lin Xiaowei', role: '文学院大三·校报主编', role_en: 'Lit Yr3 · Campus-paper Chief Editor', group: '文学院',     group_en: 'Literature',         color: '#EF5350', location_uid: 'a62839dd' },
  { id: 6, name: '何雨柔', name_en: 'He Yurou',    role: '文学院研一·校报副编辑', role_en: 'Lit M1 · Deputy Editor',           group: '文学院',     group_en: 'Literature',         color: '#EF5350', location_uid: '64a9bc35' },
  // CS
  { id: 2, name: '陈远航', name_en: 'Chen Yuanhang', role: '计算机学院研一·实验室搬砖人', role_en: 'CS M1 · Lab Workhorse',        group: '计算机学院', group_en: 'Computer Science',   color: '#42A5F5', location_uid: '3877431b' },
  { id: 11, name: '李明', name_en: 'Li Ming',       role: '计算机学院大四·算法竞赛选手', role_en: 'CS Yr4 · ACM Contestant',     group: '计算机学院', group_en: 'Computer Science',   color: '#42A5F5', location_uid: '64a9bc35' },
  // Architecture
  { id: 3, name: '苏雨桐', name_en: 'Su Yutong',    role: '建筑学院大二·社交达人',     role_en: 'Arch Yr2 · Social Butterfly',     group: '建筑学院',   group_en: 'Architecture',       color: '#66BB6A', location_uid: '8dc3960a' },
  // Philosophy
  { id: 4, name: '张鹤鸣', name_en: 'Zhang Heming', role: '哲学系博士四年级·导师助理', role_en: 'Phil PhD4 · Mentor Assistant',     group: '哲学社科',   group_en: 'Philosophy & Social Sciences', color: '#8D6E63', location_uid: '4d7a7e81' },
  // Faculty
  { id: 33, name: '王启明', name_en: 'Wang Qiming', role: '文学院教授·博导',           role_en: 'Lit Professor · PhD Supervisor',  group: '教职工',     group_en: 'Faculty',            color: '#EC407A', location_uid: '4d7a7e81' },
  { id: 34, name: '刘文博', name_en: 'Liu Wenbo',   role: '计算机学院教授',             role_en: 'CS Professor',                    group: '教职工',     group_en: 'Faculty',            color: '#EC407A', location_uid: '3877431b' },
  // Management
  { id: 22, name: '周晓琳', name_en: 'Zhou Xiaolin', role: '管理学院大三·学生会主席',   role_en: 'Mgmt Yr3 · Student Council President', group: '管理学院', group_en: 'Management',     color: '#FFA726', location_uid: 'a62839dd' },
  // Science
  { id: 17, name: '吴梓涵', name_en: 'Wu Zihan',    role: '理学院大二·数学天才',       role_en: 'Sci Yr2 · Math Prodigy',          group: '理学院',     group_en: 'Science',            color: '#AB47BC', location_uid: '64a9bc35' },
  // Arts
  { id: 27, name: '韩雪儿', name_en: 'Han Xueer',    role: '艺术学院大三·舞蹈专业',     role_en: 'Arts Yr3 · Dance Major',          group: '艺术学院',   group_en: 'Arts',               color: '#26C6DA', location_uid: '8dc3960a' },
  // Foreign Lang
  { id: 41, name: '宋恺', name_en: 'Song Kai',      role: '外语学院大二·英语专业',     role_en: 'FL Yr2 · English Major',          group: '外语学院',   group_en: 'Foreign Languages',  color: '#78909C', location_uid: '6943e822' },
  // Logistics
  { id: 56, name: '老张', name_en: 'Lao Zhang',     role: '后勤·门卫',                 role_en: 'Logistics · Gatekeeper',          group: '后勤',       group_en: 'Logistics Staff',    color: '#9E9E9E', location_uid: '438038e3' },
];

export const MOCK_RELATIONS: { edges: RelationEdge[] } = {
  edges: [
    { source: 1, target: 6,  label: '同门学姐妹',       label_en: 'Senior/junior from same advisor', color: '#4FC3F7', tone: 'focused', weight: 0.78 },
    { source: 1, target: 33, label: '师生·受指导',       label_en: 'Teacher-student · mentored',       color: '#AB47BC', tone: 'focused', weight: 0.82 },
    { source: 6, target: 33, label: '师生·考研指导',     label_en: 'Grad-exam mentorship',             color: '#AB47BC', tone: 'focused', weight: 0.82 },
    { source: 1, target: 56, label: '校报同事+文友',     label_en: 'Newspaper colleagues',             color: '#4FC3F7', tone: 'focused', weight: 0.7 },
    { source: 56, target: 33, label: '熟人',             label_en: 'Acquaintance',                     color: '#E0E0E0', tone: 'casual',  weight: 0.4 },
    { source: 2, target: 34, label: '导师-研究生',       label_en: 'Advisor - Grad student',           color: '#AB47BC', tone: 'focused', weight: 0.82 },
    { source: 2, target: 11, label: '同窗合作',           label_en: 'Coursework collaboration',         color: '#FF8A65', tone: 'decisive',weight: 0.74 },
    { source: 11, target: 17, label: '竞赛对手',         label_en: 'Contest rivals',                   color: '#FF7043', tone: 'tense',   weight: 0.65 },
    { source: 17, target: 33, label: '受讲座启发',       label_en: 'Inspired by talks',                color: '#FFD54F', tone: 'curious', weight: 0.6 },
    { source: 3, target: 27, label: '社团活动伙伴',       label_en: 'Club activity partners',           color: '#66BB6A', tone: 'warm',    weight: 0.7 },
    { source: 22, target: 1, label: '学生会-校报联络',   label_en: 'Council-paper liaison',            color: '#FF8A65', tone: 'decisive',weight: 0.74 },
    { source: 22, target: 27, label: '暧昧',              label_en: 'Attraction',                       color: '#E91E63', tone: 'playful', weight: 0.72 },
    { source: 41, target: 1,  label: '偶遇·读书会',      label_en: 'Chance · book club',               color: '#E0E0E0', tone: 'casual',  weight: 0.4 },
    { source: 4, target: 33,  label: '同门师弟',          label_en: 'Junior from same lab',             color: '#4FC3F7', tone: 'focused', weight: 0.78 },
    { source: 4, target: 17,  label: '哲学课助教',        label_en: 'TA for philosophy class',          color: '#AB47BC', tone: 'focused', weight: 0.82 },
  ],
};

export const MOCK_SCENES: { scenes: SceneEntry[] } = {
  scenes: [
    {
      id: 's1', title: '校报编辑会',
      title_en: 'Newspaper editorial meeting',
      tags: ['学术', '日常'],
      people: [1, 6, 33], trigger: '周一下午例会 / Monday weekly review',
      narrative_zh: '林晓薇主持选题，何雨柔记录，王启明偶尔点评。',
      narrative_en: 'Xiaowei chairs topic picking; Yurou takes notes; Prof Wang chimes in.',
      weather: 'clear', space_zh: '校报编辑室', space_en: 'Newsroom', time_band: '14:00-16:00', weekday_pattern: 'Mon',
    },
    {
      id: 's2', title: '咖啡馆灵感时间',
      title_en: 'Coffee-shop inspiration window',
      tags: ['日常', '社交'],
      people: [1, 41], trigger: '下午茶时间 / Afternoon coffee',
      narrative_zh: '林晓薇和宋恺在咖啡馆相遇，聊起最近读的书。',
      narrative_en: 'Xiaowei and Song Kai bump into each other and chat about books.',
      weather: 'overcast', space_zh: '咖啡馆', space_en: 'Café', time_band: '16:00-18:00', weekday_pattern: 'Wed',
    },
    {
      id: 's3', title: '算法竞赛集训',
      title_en: 'ACM training session',
      tags: ['学术'],
      people: [2, 11, 17, 34], trigger: '周末集训 / Weekend training',
      narrative_zh: '李明、陈远航与刘文博一起讨论难题，吴梓涵从数学角度切入。',
      narrative_en: 'Li Ming, Chen Yuanhang and Prof Liu wrestle with hard problems; Wu Zihan brings a math view.',
      weather: 'rain', space_zh: '机房', space_en: 'Lab', time_band: '10:00-17:00', weekday_pattern: 'Sat',
    },
  ],
};

export const MOCK_TIMELINE: { events: TimelineEvent[] } = {
  events: [
    { day: '周一', time: '14:30', ts: '2026-05-25T14:30', title: '校报编辑会开始', title_en: 'Editorial meeting starts',
      location_uid: '4d7a7e81', people: [1, 6, 33],
      narrative_zh: '林晓薇宣布本周选题：校园里的微光。',
      narrative_en: 'Xiaowei opens this week\'s theme: campus glows.' },
    { day: '周二', time: '10:00', ts: '2026-05-26T10:00', title: 'ACM 集训', title_en: 'ACM training',
      location_uid: '3877431b', people: [2, 11],
      narrative_zh: '陈远航和李明在实验室里互怼调试。',
      narrative_en: 'Chen Yuanhang and Li Ming argue while debugging.' },
    { day: '周三', time: '16:30', ts: '2026-05-27T16:30', title: '咖啡馆相遇', title_en: 'Coffee-shop encounter',
      location_uid: 'a62839dd', people: [1, 41],
      narrative_zh: '林晓薇与宋恺在咖啡馆相遇并交换书单。',
      narrative_en: 'Xiaowei meets Song Kai over coffee and swaps reading lists.' },
    { day: '周四', time: '20:00', ts: '2026-05-28T20:00', title: '社团活动', title_en: 'Club night',
      location_uid: '8dc3960a', people: [3, 27],
      narrative_zh: '苏雨桐与韩雪儿一起组织舞蹈快闪。',
      narrative_en: 'Su Yutong and Han Xueer co-host a dance flashmob.' },
    { day: '周五', time: '13:00', ts: '2026-05-29T13:00', title: '哲学讨论', title_en: 'Philosophy seminar',
      location_uid: '4d7a7e81', people: [4, 17, 33],
      narrative_zh: '张鹤鸣带领讨论，吴梓涵抛出数学化诠释。',
      narrative_en: 'Heming leads; Wu Zihan offers a math reading.' },
  ],
};

export const MOCK_SCENE_GRAPH: SceneGraphResponseLite = {
  rooms: [
    { uid: 'a7934434', index: 0,  name: 'Kitchen',         tag: ['daily life'],          adjacent: ['438038e3','6943e822','8dc3960a'], description: 'Cooking area',          position: [79.6,9.6,0],  containment: 10, furniture: [] },
    { uid: '9a49343c', index: 1,  name: 'Dining Area',     tag: ['daily life','social'], adjacent: ['438038e3','a62839dd'],            description: 'Dining',                position: [54.1,9.6,0],  containment: 80, furniture: [] },
    { uid: '99883bc6', index: 2,  name: 'Discussion Area', tag: ['study','social'],      adjacent: ['438038e3','4d7a7e81','7a281fd7','a62839dd'], description: 'Discussion',  position: [5.8,44.1,0],  containment: 20, furniture: [] },
    { uid: '3877431b', index: 3,  name: 'Lab Area',        tag: ['study'],               adjacent: ['4d7a7e81','4ef146d8','64a9bc35','66cb10e7','7a281fd7','cb0199d8'], description: 'Lab', position: [33.6,90.4,0], containment: 30, furniture: [] },
    { uid: '6943e822', index: 4,  name: 'Halal Restaurant',tag: ['daily life','social'], adjacent: ['438038e3','a7934434'],            description: 'Halal restaurant',      position: [140.8,3.4,4], containment: 50, furniture: [] },
    { uid: '8dc3960a', index: 5,  name: 'Club Activities', tag: ['social','leisure'],    adjacent: ['438038e3','a7934434'],            description: 'Club activities',       position: [91.4,14.2,4], containment: 40, furniture: [] },
    { uid: 'a62839dd', index: 6,  name: 'Café',            tag: ['leisure','social','daily life'], adjacent: ['438038e3','7a281fd7','99883bc6','9a49343c'], description: 'Café', position: [60.2,17.7,4], containment: 30, furniture: [] },
    { uid: '4d7a7e81', index: 7,  name: 'Classroom',       tag: ['study'],               adjacent: ['3877431b','438038e3','4ef146d8','64a9bc35','7a281fd7','99883bc6'], description: 'Classroom', position: [9.9,87.7,4], containment: 40, furniture: [] },
    { uid: '9a4098e7', index: 8,  name: 'Discussion Area', tag: ['study','social'],      adjacent: [],                                  description: 'Discussion 2',         position: [14.8,97.1,4], containment: 20, furniture: [] },
    { uid: '66cb10e7', index: 9,  name: 'Garden Space',    tag: ['leisure','fitness'],   adjacent: ['3877431b','4ef146d8','64a9bc35'],  description: 'Garden',               position: [42.9,136.1,4], containment: 60, furniture: [] },
    { uid: 'cb0199d8', index: 10, name: 'Lecture Hall',    tag: ['study','social'],      adjacent: ['3877431b','64a9bc35'],            description: 'Lecture',               position: [79,108.8,4], containment: 150, furniture: [] },
    { uid: '438038e3', index: 11, name: 'Dorm Rooms',      tag: ['daily life','study'],  adjacent: ['4d7a7e81','6943e822','8dc3960a','99883bc6','9a49343c','a62839dd','a7934434'], description: 'Dorms', position: [62.5,7,8], containment: 4, furniture: [] },
    { uid: 'da2afe02', index: 12, name: 'Discussion Area', tag: ['study','social'],      adjacent: [],                                  description: 'Discussion 3',         position: [62.5,9,8],   containment: 16, furniture: [] },
    { uid: '7a281fd7', index: 13, name: 'Garden Space',    tag: ['leisure','fitness'],   adjacent: ['3877431b','4d7a7e81','99883bc6','a62839dd'], description: 'Rooftop garden',  position: [10.1,58.2,8],containment: 50, furniture: [] },
    { uid: '64a9bc35', index: 14, name: 'Study Area',      tag: ['study'],               adjacent: ['3877431b','4d7a7e81','66cb10e7','cb0199d8'], description: 'Silent study',     position: [50.7,112.7,8],containment: 60, furniture: [] },
    { uid: '4ef146d8', index: 15, name: 'Café',            tag: ['leisure','daily life'],adjacent: ['3877431b','4d7a7e81','66cb10e7'],  description: 'Library café',         position: [10.3,108.3,8],containment: 20, furniture: [] },
  ],
};

interface SceneGraphResponseLite { rooms: Room[]; }

/** A small persona body for the offline detail panel. */
export function mockAgentDetail(id: string | number) {
  const lite = MOCK_AGENTS.find(a => String(a.id) === String(id)) || MOCK_AGENTS[0];
  return {
    ...lite,
    profile: {
      age: 21, mbti: 'INFP', ocean: 'O90 C55 E35 A80 N65',
      innate: '富有想象力、共情力强',
      innate_en: 'Imaginative, empathetic',
      learned: '长期写作训练形成的敏锐观察力',
      learned_en: 'Keen observation honed by long-term writing',
      belief: '文字是理解世界最诚实的方式',
      belief_en: 'Words are the most honest way to understand the world',
      goal: '出版自己的第一本短篇小说集',
      goal_en: 'Publish a first short-story collection',
      contradiction: '渴望被阅读 vs 害怕被误读',
      contradiction_en: 'Crave readers vs fear misreading',
      surface: '温和安静、礼貌得体',
      surface_en: 'Gentle, polite',
      deep: '内心戏剧化，渴望深度连接却害怕暴露',
      deep_en: 'Inner drama, longs for depth but fears exposure',
      fear: '作品被忽视',
      fear_en: 'Work being ignored',
      desire: '被真正理解',
      desire_en: 'To be truly understood',
      bias: '倾向把人多的地方看成素材丰富',
      bias_en: 'Sees crowded places as material-rich',
      narrative: '我不是在发呆，我是在采集素材',
      narrative_en: 'Not zoning out — collecting material',
      lifestyle: '晚睡晚起型，夜间创作效率最高',
      lifestyle_en: 'Night owl, peak creativity at night',
      rhythm: '上午缓慢启动，下午平稳，夜间爆发',
      rhythm_en: 'Slow morning, steady afternoon, night burst',
      spaces: '图书馆四楼角落、咖啡厅靠窗位、校报编辑室',
      spaces_en: 'Library 4F corner, café window seat, newsroom',
      group_zh: lite.group, group_en: lite.group_en,
      schedule: [
        '07:30 赖床刷手机',
        '09:00 图书馆四楼占座·读书',
        '11:30 食堂午饭',
        '14:00 校报编辑室开会',
        '16:00 咖啡厅写稿',
        '20:00 宿舍继续写作',
      ],
    },
    location_uid: lite.location_uid,
    perception: { children: [], siblings: [] },
  };
}

export function mockAgentMemory(_id: string | number) {
  return {
    short_term: [
      { id: 1, ts: '2026-05-26T09:30', text: '在图书馆遇到何雨柔，一起讨论选题', tone: 'warm', hit_count: 3 },
      { id: 2, ts: '2026-05-26T10:15', text: '想到一个关于校园光影的句子，记下来', tone: 'curious', hit_count: 1 },
    ],
    long_term: [
      { id: 'l1', ts: '2026-05-23T18:00', text: '王启明老师批改了我的散文，给了三处具体建议', tone: 'focused', hit_count: 6, degraded: false },
      { id: 'l2', ts: '2026-05-22T22:00', text: '与室友夜聊到凌晨', tone: 'casual', hit_count: 2, degraded: true },
    ],
    graph: [
      { subject: '林晓薇', predicate: '请教', object: '王启明', tone: 'focused' },
      { subject: '林晓薇', predicate: '同事',   object: '何雨柔', tone: 'warm' },
      { subject: '林晓薇', predicate: '偶遇',   object: '宋恺',   tone: 'casual' },
    ],
  };
}

export function mockAgentSchedule(_id: string | number) {
  const slots: any[] = [];
  const start = new Date('2026-05-26T00:00:00');
  for (let i = 0; i < 288; i++) {
    const t = new Date(start.getTime() + i * 5 * 60 * 1000);
    const e = new Date(t.getTime() + 5 * 60 * 1000);
    let kind: 'template' | 'fragment' | 'empty' = 'empty';
    let act = '';
    if (i >= 90 && i < 102)      { kind = 'template'; act = '图书馆读书'; }
    else if (i >= 138 && i < 144) { kind = 'fragment'; act = '食堂午饭'; }
    else if (i >= 168 && i < 192) { kind = 'template'; act = '校报会议'; }
    else if (i >= 192 && i < 216) { kind = 'fragment'; act = '咖啡厅写稿'; }
    slots.push({ index: i, start: t.toISOString(), end: e.toISOString(), kind, activity: act, location_uid: 'a62839dd', source_id: 's1' });
  }
  return { day: '2026-05-26', slots };
}

export function mockAgentHistory(_id: string | number) {
  return [
    { ts: '2026-05-26T08:30', action_id: 'goto', params: { uid: 'a62839dd' }, ok: true,  note: '前往咖啡厅' },
    { ts: '2026-05-26T09:00', action_id: 'read', params: { item: 'book' },   ok: true,  note: '' },
    { ts: '2026-05-26T11:15', action_id: 'chat', params: { with: 6 },         ok: true,  note: '与何雨柔讨论选题' },
    { ts: '2026-05-26T14:05', action_id: 'goto', params: { uid: '4d7a7e81' }, ok: false, note: '路径阻塞，回退' },
  ];
}

export function mockAgentPerception(_id: string | number) {
  return {
    here: 'a62839dd',
    children: [
      { uid: 'a62839dd', name: 'Café', agents: ['林晓薇', '宋恺'], items: ['café table', 'chair'] },
    ],
    siblings: [
      { uid: '99883bc6', name: 'Discussion Area', agents: [], items: ['round table'] },
      { uid: '7a281fd7', name: 'Garden Space',    agents: ['苏雨桐'], items: ['outdoor bench'] },
    ],
  };
}

export const MOCK_WORLD = {
  sim_time: '2026-05-26T10:00:00',
  agents: MOCK_AGENTS.map(a => ({ id: a.id, name: a.name, location_uid: a.location_uid })),
  items: [],
};
