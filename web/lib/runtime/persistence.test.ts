import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { BrowserPlayRuntime } from './browser-runtime';
import type { HandPayload, RuntimeRequest } from './contracts';

class MemoryStorage {
  private values = new Map<string, string>();
  getItem(key: string) {
    return this.values.get(key) ?? null;
  }
  setItem(key: string, value: string) {
    this.values.set(key, value);
  }
  removeItem(key: string) {
    this.values.delete(key);
  }
  clear() {
    this.values.clear();
  }
  key(index: number) {
    return [...this.values.keys()][index] ?? null;
  }
  get length() {
    return this.values.size;
  }
}

const unavailableRemote: RuntimeRequest = async () => {
  throw new Error('Remote API unavailable');
};

describe('browser game persistence', () => {
  beforeEach(() => vi.stubGlobal('localStorage', new MemoryStorage()));
  afterEach(() => vi.unstubAllGlobals());

  it('restores the current hand and selected model in a fresh runtime', async () => {
    const firstRuntime = new BrowserPlayRuntime(unavailableRemote);
    const created = await firstRuntime.request<HandPayload>('/v1/hands', {
      method: 'POST',
      body: JSON.stringify({ seed: 91, botProvider: 'check-call-hu' }),
    });
    await firstRuntime.request(`/v1/hands/${created.sessionId}/bot-provider`, {
      method: 'POST',
      body: JSON.stringify({ providerId: 'uniform-random-hu' }),
    });

    const secondRuntime = new BrowserPlayRuntime(unavailableRemote);
    const restored = await secondRuntime.request<{ hand: HandPayload | null }>(
      '/v1/hands/current',
    );

    expect(restored.hand?.sessionId).toBe(created.sessionId);
    expect(restored.hand?.observation).toEqual(created.observation);
    expect(restored.hand?.botProvider).toBe('uniform-random-hu');
  });
});
