import { defineStore } from 'pinia';
import { ref, computed } from 'vue';

export type Lang = 'zh' | 'en';

/**
 * Global bilingual switch. Persists choice in localStorage.
 * Components consume `lang.value` and the `t(zh, en)` helper.
 */
export const useLangStore = defineStore('lang', () => {
  const stored = (typeof localStorage !== 'undefined' && localStorage.getItem('npcGraphLang')) as Lang | null;
  const lang = ref<Lang>(stored === 'en' ? 'en' : 'zh');

  function set(next: Lang) {
    lang.value = next;
    try { localStorage.setItem('npcGraphLang', next); } catch { /* ignore */ }
    if (typeof document !== 'undefined') {
      document.documentElement.lang = next === 'en' ? 'en' : 'zh-CN';
    }
  }
  function toggle() {
    set(lang.value === 'zh' ? 'en' : 'zh');
  }

  /** Pick the language-appropriate field on an object with `_en` suffix fallback. */
  function pickField<T extends Record<string, any>>(obj: T | null | undefined, base: string): any {
    if (!obj) return undefined;
    if (lang.value === 'en') return obj[base + '_en'] ?? obj[base];
    return obj[base];
  }

  /** Inline translate helper. */
  function t(zh: string, en: string): string {
    return lang.value === 'en' ? en : zh;
  }

  /** Opposite-language label for the toggle button. */
  const otherLabel = computed(() => (lang.value === 'zh' ? 'EN' : '中'));

  return { lang, set, toggle, t, pickField, otherLabel };
});
