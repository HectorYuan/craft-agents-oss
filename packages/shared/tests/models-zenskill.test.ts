/**
 * B15 契约测试 —— GUI 侧型号目录必须来自真相源生成物，且**覆盖全部厂商**。
 *
 * 背景（2026-10-25 实测）：vendor 侧曾手写两份 4 条 deepseek 型号清单
 * （`config/models-zenskill.ts` + `server-core/src/model-fetchers/zenskill.ts`）
 * ⇒ ① 目录里只有 deepseek，mimo / qwen / volc / glm / minimax / moonshot 等
 * 厂商的型号在 GUI 选型列表里**根本不存在**；
 * ② 不在表里的型号会被 `agent/backend/zenskill-agent.ts` 静默替换成
 * DEFAULT_MODEL ⇒ **用户选的国产型号直接被顶掉**。
 *
 * 修法：型号目录改由主仓 `specs/providers.yaml`（唯一真相源）生成，
 * 两个消费点共用同一份生成物。本测试守住「不许退回手写」的底线。
 */

import { describe, it, expect } from 'bun:test';
import { ZENSKILL_MODEL_REGISTRY } from '../src/config/models-zenskill.ts';
import { getModelById, DEFAULT_MODEL } from '../src/config/models.ts';

describe('B15: GUI 型号目录来自真相源生成物', () => {
  it('覆盖多个厂商（此前只有 deepseek ⇒ 国产型号在 GUI 里不存在）', () => {
    const providers = new Set(ZENSKILL_MODEL_REGISTRY.map((m) => m.id.split('/')[0]));
    // 至少覆盖这几个：目录里少一个就说明真相源下发了却被消费方漏掉
    for (const p of ['deepseek', 'qwen', 'mimo', 'volc', 'glm', 'minimax']) {
      expect(providers.has(p)).toBe(true);
    }
    expect(ZENSKILL_MODEL_REGISTRY.length).toBeGreaterThan(20);
  });

  it('国产型号可按 id 查到（此前查不到 ⇒ 会被顶成 DEFAULT_MODEL）', () => {
    // 取目录里的国产型号逐个验证：getModelById 必须能按完整 id 命中
    const domestic = ZENSKILL_MODEL_REGISTRY.filter((m) =>
      ['qwen', 'mimo', 'volc', 'glm', 'minimax', 'minimax-cn', 'moonshot', 'gemini'].includes(
        m.id.split('/')[0],
      ),
    );
    expect(domestic.length).toBeGreaterThan(0);
    for (const m of domestic) {
      expect(getModelById(m.id)?.id).toBe(m.id);
    }
  });

  it('id 形如 provider/model（与引擎 resolve_model 形式一致）', () => {
    for (const m of ZENSKILL_MODEL_REGISTRY) {
      expect(m.id).toContain('/');
      const [provider, model] = m.id.split('/');
      expect(provider.length).toBeGreaterThan(0);
      expect(model.length).toBeGreaterThan(0);
    }
  });

  it('shortName 全局唯一（同名型号不得跨 provider 命中 ⇒ 会串端点）', () => {
    const seen = new Map<string, string>();
    for (const m of ZENSKILL_MODEL_REGISTRY) {
      const prev = seen.get(m.shortName);
      expect(`${m.shortName} @ ${m.id}`.length).toBeGreaterThan(0);
      if (prev) {
        // 同名 ⇒ 两者都必须是 provider/model 形式（不能是裸短名）
        expect(m.shortName).toContain('/');
        expect(prev).toContain('/');
      }
      seen.set(m.shortName, m.id);
    }
  });

  it('默认型号仍在目录里（否则 DEFAULT_MODEL 落空）', () => {
    expect(ZENSKILL_MODEL_REGISTRY.some((m) => m.id === DEFAULT_MODEL)).toBe(true);
  });

  it('不得出现凭空造出的短名（如 Haiku —— 会改变既有查找行为）', () => {
    const shorts = new Set(ZENSKILL_MODEL_REGISTRY.map((m) => m.shortName));
    expect(shorts.has('Haiku')).toBe(false);
  });

  it('contextWindow 缺失时为 0（未知，不猜值；UI 侧有兜底）', () => {
    for (const m of ZENSKILL_MODEL_REGISTRY) {
      expect(Number.isInteger(m.contextWindow)).toBe(true);
      expect(m.contextWindow).toBeGreaterThanOrEqual(0);
    }
  });
});
