import { createRouter, createWebHashHistory } from 'vue-router';

export const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/', redirect: '/relations' },
    { path: '/relations', component: () => import('@/views/RelationView.vue') },
    { path: '/scene', component: () => import('@/views/SceneGraphView.vue') },
    { path: '/agent', component: () => import('@/views/AgentDetailView.vue') },
    { path: '/agent/:id', component: () => import('@/views/AgentDetailView.vue') },
    { path: '/memory-graph', component: () => import('@/views/MemoryGraphView.vue') },
    { path: '/timeline', component: () => import('@/views/TimelineView.vue') },
  ],
});
