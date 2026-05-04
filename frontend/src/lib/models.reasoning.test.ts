import { describe, expect, it } from 'vitest'

import {
  clampReasoningEffort,
  supportedReasoningEffortsForModel,
  supportsConfigurableReasoning,
} from './models'

describe('provider/model reasoning effort support', () => {
  it('disables unsupported global effort values for Fireworks Kimi and non-reasoning models', () => {
    expect(supportedReasoningEffortsForModel('fireworks', 'accounts/fireworks/models/kimi-k2p5')).toEqual(['none'])
    expect(supportsConfigurableReasoning('fireworks', 'accounts/fireworks/models/kimi-k2p5')).toBe(false)
    expect(clampReasoningEffort('fireworks', 'accounts/fireworks/models/kimi-k2p5', 'medium')).toBe('none')

    expect(supportedReasoningEffortsForModel('chronos', 'nvidia/nemotron-3-super-120b-a12b:free')).toEqual(['none'])
    expect(clampReasoningEffort('chronos', 'nvidia/nemotron-3-super-120b-a12b:free', 'high')).toBe('none')
  })

  it('keeps OpenAI GPT-5 minimal effort and clamps xhigh for standard providers', () => {
    expect(supportedReasoningEffortsForModel('openai', 'gpt-5')).toEqual(['none', 'minimal', 'low', 'medium', 'high'])
    expect(clampReasoningEffort('openai', 'gpt-5', 'minimal')).toBe('minimal')

    expect(supportedReasoningEffortsForModel('google', 'gemini-2.5-pro')).toEqual(['none', 'low', 'medium', 'high'])
    expect(clampReasoningEffort('google', 'gemini-2.5-pro', 'xhigh')).toBe('high')
    expect(clampReasoningEffort('xai', 'grok-3-mini', 'minimal')).toBe('low')
  })
})
