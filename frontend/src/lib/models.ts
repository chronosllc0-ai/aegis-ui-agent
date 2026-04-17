// ── Provider + Model catalogue ───────────────────────────────────────
// Last updated: 2026-03-24 - sourced from official provider docs

import { createElement } from 'react'

// ── Provider icon URLs (hosted on postimg) ────────────────────────
export const PROVIDER_ICON_URLS: Record<string, string> = {
  google:     'https://i.postimg.cc/2SwWrKwz/download_1.jpg',
  openai:     'https://i.postimg.cc/d3HRsSv7/download_2.png',
  anthropic:  'https://i.postimg.cc/L6yVy6b3/2eb79382ad63416682dcc08c91fcc46f.png',
  xai:        'https://i.postimg.cc/zvbZ76dr/download.png',
  openrouter: 'https://i.postimg.cc/QdMMqLYZ/openrouter_icon.png',
  fireworks: 'https://fireworks.ai/favicon.ico',
}

// Chronos AI logo
export const CHRONOS_LOGO_URL = 'https://i.postimg.cc/FRyC2G1k/IMG_20260103_192235_443.webp'

export type ModelInfo = {
  id: string
  label: string
  description: string
  vision?: boolean
  reasoning?: boolean           // true = model supports reasoning/thinking tokens
  reasoningModes?: Array<'medium' | 'high' | 'extended' | 'adaptive'>
  contextLength: number  // max context window in tokens
}

export type ProviderInfo = {
  id: string
  displayName: string
  models: ModelInfo[]
  iconUrl: string
  keyPrefix: string
  gatewayOnly?: boolean
}

export const PROVIDERS: ProviderInfo[] = [
  // ── Chronos Gateway ─────────────────────────────────────────────────
  {
    id: 'chronos',
    displayName: 'Chronos Gateway',
    iconUrl: CHRONOS_LOGO_URL,
    keyPrefix: '',
    gatewayOnly: true,
    models: [
      { id: 'nvidia/nemotron-3-super-120b-a12b:free', label: 'Nemotron 3 Super (Free)', description: 'Free · NVIDIA 1M context · Best to start with', vision: false, contextLength: 1_000_000 },
      { id: 'openai/gpt-5.4', label: 'GPT-5.4', description: "OpenAI's latest frontier model", vision: true, contextLength: 1_048_576 },
      { id: 'openai/gpt-5.4-mini', label: 'GPT-5.4 Mini', description: 'Fast, cost-efficient GPT-5.4', vision: true, contextLength: 400_000 },
      { id: 'openai/gpt-5.4-nano', label: 'GPT-5.4 Nano', description: 'Lightest GPT-5.4 variant', vision: true, contextLength: 400_000 },
      { id: 'openai/gpt-5.3-codex', label: 'GPT-5.3 Codex', description: 'Best agentic coding model', vision: false, contextLength: 400_000 },
      { id: 'anthropic/claude-opus-4.6', label: 'Claude Opus 4.6', description: 'Most intelligent for long tasks', vision: true, contextLength: 1_000_000 },
      { id: 'anthropic/claude-sonnet-4-20250514', label: 'Claude Sonnet 4', description: 'Balanced speed + intelligence', vision: true, contextLength: 200_000 },
      { id: 'x-ai/grok-4.20-beta', label: 'Grok 4.20 Beta', description: 'xAI flagship with 2M context', vision: true, contextLength: 2_000_000 },
      { id: 'google/gemini-3.1-pro-preview', label: 'Gemini 3.1 Pro', description: 'Best Gemini with tool accuracy', vision: true, reasoning: true, contextLength: 1_048_576 },
      { id: 'qwen/qwen3-max-thinking', label: 'Qwen3 Max Thinking', description: 'Flagship reasoning from Qwen3', vision: false, reasoning: true, contextLength: 262_144 },
      { id: 'qwen/qwen3-next-80b-a3b-instruct:free', label: 'Qwen3 Next 80B A3B Instruct (Free)', description: 'Free Qwen3 Next instruct model via OpenRouter.', vision: false, contextLength: 262_144 },
      { id: 'qwen/qwen3-coder:free', label: 'Qwen3 Coder (Free)', description: 'Free Qwen3 Coder model tuned for coding workloads.', vision: false, contextLength: 262_144 },
      { id: 'google/gemma-4-26b-a4b-it:free', label: 'Gemma 4 26B A4B (Free)', description: 'Free Gemma 4 26B instruction-tuned model.', vision: false, contextLength: 262_144 },
      { id: 'google/gemma-4-31b-it:free', label: 'Gemma 4 31B (Free)', description: 'Free Gemma 4 31B instruction-tuned model.', vision: false, contextLength: 262_144 },
      { id: 'nvidia/nemotron-nano-9b-v2:free', label: 'Nemotron Nano 9B V2 (Free)', description: 'Free NVIDIA Nemotron Nano v2 for lightweight tasks.', vision: false, contextLength: 128_000 },
      { id: 'minimax/minimax-m2.5:free', label: 'MiniMax M2.5 (Free)', description: 'Free MiniMax M2.5 model for general productivity tasks.', vision: false, contextLength: 196_608 },
      { id: 'z-ai/glm-4.5-air:free', label: 'GLM 4.5 Air (Free)', description: 'Free GLM 4.5 Air model by Z.ai.', vision: false, contextLength: 131_072 },
      { id: 'mistralai/mistral-small-4', label: 'Mistral Small 4', description: 'Lean European model, 128K context', vision: false, contextLength: 128_000 },
      { id: 'nvidia/nemotron-3-super-120b-a12b', label: 'Nemotron 3 Super', description: 'NVIDIA 120B param, 1M context', vision: false, contextLength: 1_000_000 },
    ],
  },
  // ── Google ──────────────────────────────────────────────────────────
  {
    id: 'google',
    displayName: 'Google (Gemini)',
    iconUrl: PROVIDER_ICON_URLS.google,
    keyPrefix: '',
    models: [
      { id: 'gemini-3.1-pro-preview', label: 'Gemini 3.1 Pro Preview', description: 'Latest Gemini 3 series - cutting-edge reasoning & multimodal.', vision: true, reasoning: true, contextLength: 2_000_000 },
      { id: 'gemini-3.1-flash-lite-preview', label: 'Gemini 3.1 Flash-Lite Preview', description: 'First Flash-Lite in the Gemini 3 series - ultra-fast.', vision: true, contextLength: 1_000_000 },
      { id: 'gemini-3-flash-preview', label: 'Gemini 3 Flash Preview', description: 'Frontier-class speed that rivals larger models.', vision: true, contextLength: 1_000_000 },
      { id: 'gemini-2.5-pro', label: 'Gemini 2.5 Pro', description: 'Stable production model - best quality + complex reasoning.', vision: true, reasoning: true, contextLength: 1_048_576 },
      { id: 'gemini-2.5-flash', label: 'Gemini 2.5 Flash', description: 'Stable production model - fast responses, lower latency.', vision: true, reasoning: true, contextLength: 1_048_576 },
    ],
  },
  // ── OpenAI ──────────────────────────────────────────────────────────
  {
    id: 'openai',
    displayName: 'OpenAI',
    iconUrl: PROVIDER_ICON_URLS.openai,
    keyPrefix: 'sk-',
    models: [
      { id: 'gpt-5.2', label: 'GPT-5.2', description: 'Flagship - best for coding and agentic tasks.', vision: true, contextLength: 256_000 },
      { id: 'gpt-5.2-pro', label: 'GPT-5.2 Pro', description: 'Smarter, more precise responses on complex tasks.', vision: true, contextLength: 256_000 },
      { id: 'gpt-5', label: 'GPT-5', description: 'Intelligent reasoning model with configurable effort.', vision: true, contextLength: 256_000 },
      { id: 'gpt-5-mini', label: 'GPT-5 Mini', description: 'Fast, cost-efficient version of GPT-5.', vision: true, contextLength: 256_000 },
      { id: 'gpt-5-nano', label: 'GPT-5 Nano', description: 'Fastest, most cost-efficient GPT-5 variant.', vision: true, contextLength: 128_000 },
      { id: 'gpt-4.1', label: 'GPT-4.1', description: 'Smartest non-reasoning model.', vision: true, contextLength: 1_047_576 },
      { id: 'gpt-4.1-mini', label: 'GPT-4.1 Mini', description: 'Fast and cost-effective.', vision: true, contextLength: 1_047_576 },
      { id: 'gpt-4.1-nano', label: 'GPT-4.1 Nano', description: 'Ultra-lightweight.', vision: true, contextLength: 1_047_576 },
      { id: 'o4-mini', label: 'o4-mini', description: 'Advanced reasoning, compact.', vision: true, reasoning: true, contextLength: 200_000 },
      { id: 'o3', label: 'o3', description: 'Deep reasoning model.', vision: true, reasoning: true, contextLength: 200_000 },
    ],
  },
  // ── Anthropic ───────────────────────────────────────────────────────
  {
    id: 'anthropic',
    displayName: 'Anthropic',
    iconUrl: PROVIDER_ICON_URLS.anthropic,
    keyPrefix: 'sk-ant-',
    models: [
      { id: 'claude-opus-4-6', label: 'Claude Opus 4.6', description: 'Most intelligent - agents and coding. 1M context.', vision: true, reasoning: true, contextLength: 1_000_000 },
      { id: 'claude-sonnet-4-6', label: 'Claude Sonnet 4.6', description: 'Best combo of speed + intelligence. 1M context.', vision: true, reasoning: true, contextLength: 1_000_000 },
      { id: 'claude-haiku-4-5', label: 'Claude Haiku 4.5', description: 'Fastest Anthropic model - near-frontier intelligence.', vision: true, reasoning: true, contextLength: 200_000 },
      { id: 'claude-sonnet-4-20250514', label: 'Claude Sonnet 4', description: 'Previous generation balanced model.', vision: true, reasoning: true, contextLength: 200_000 },
      { id: 'claude-3.5-sonnet-20241022', label: 'Claude 3.5 Sonnet', description: 'Excellent code and reasoning.', vision: true, contextLength: 200_000 },
    ],
  },
  // ── xAI ─────────────────────────────────────────────────────────────
  {
    id: 'xai',
    displayName: 'xAI',
    iconUrl: PROVIDER_ICON_URLS.xai,
    keyPrefix: 'xai-',
    models: [
      { id: 'grok-4-20250720', label: 'Grok 4', description: "xAI's most capable frontier model - best for complex reasoning.", vision: true, contextLength: 256_000 },
      { id: 'grok-4.20-beta', label: 'Grok 4.20 Beta', description: "xAI's newest flagship model with industry-leading speed and intelligence.", vision: true, contextLength: 2_000_000 },
      { id: 'grok-4.20-multi-agent-beta', label: 'Grok 4.20 Multi-Agent Beta', description: 'Variant of Grok 4.20 designed for collaborative multi-agent workflows.', vision: true, contextLength: 2_000_000 },
      { id: 'grok-3', label: 'Grok 3', description: 'xAI flagship - strong reasoning and coding.', vision: true, contextLength: 131_072 },
      { id: 'grok-3-mini', label: 'Grok 3 Mini', description: 'Efficient, cost-effective Grok 3 variant.', vision: false, reasoning: true, contextLength: 131_072 },
      { id: 'grok-3-mini-fast', label: 'Grok 3 Mini Fast', description: 'Ultra-fast variant of Grok 3 Mini.', vision: false, reasoning: true, contextLength: 131_072 },
      { id: 'grok-2-vision-1212', label: 'Grok 2 Vision', description: 'Previous generation with vision capabilities.', vision: true, contextLength: 32_768 },
    ],
  },
  // ── Fireworks AI ────────────────────────────────────────────────────
  {
    id: 'fireworks',
    displayName: 'Fireworks AI',
    iconUrl: PROVIDER_ICON_URLS.fireworks,
    keyPrefix: '',
    models: [
      { id: 'accounts/fireworks/models/kimi-k2p5', label: 'Kimi K2.5', description: 'Moonshot AI Kimi K2.5 with native reasoning via Fireworks AI.', vision: false, reasoning: true, contextLength: 262_144 },
      { id: 'accounts/fireworks/models/kimi-k2-instruct-0905', label: 'Kimi K2 Instruct', description: 'Moonshot AI Kimi K2 Instruct model on Fireworks AI.', vision: false, contextLength: 128_000 },
    ],
  },
  // ── OpenRouter ──────────────────────────────────────────────────────
  {
    id: 'openrouter',
    displayName: 'OpenRouter',
    iconUrl: PROVIDER_ICON_URLS.openrouter,
    keyPrefix: 'sk-or-',
    models: [
      { id: 'openai/gpt-5.4-pro', label: 'GPT-5.4 Pro', description: "OpenAI's most advanced model via OpenRouter.", vision: true, contextLength: 1_048_576 },
      { id: 'openai/gpt-5.4', label: 'GPT-5.4', description: "OpenAI's latest frontier model - unifying Codex and GPT lines.", vision: true, contextLength: 1_048_576 },
      { id: 'openai/gpt-5.4-mini', label: 'GPT-5.4 Mini', description: 'Faster, cost-efficient GPT-5.4 variant.', vision: true, contextLength: 400_000 },
      { id: 'openai/gpt-5.4-nano', label: 'GPT-5.4 Nano', description: 'Most lightweight and cost-efficient GPT-5.4 variant.', vision: true, contextLength: 400_000 },
      { id: 'openai/gpt-5.3-codex', label: 'GPT-5.3 Codex', description: "OpenAI's most advanced agentic coding model.", vision: false, contextLength: 400_000 },
      { id: 'anthropic/claude-opus-4.6', label: 'Claude Opus 4.6', description: "Anthropic's strongest model for coding and long-running tasks.", vision: true, contextLength: 1_000_000 },
      { id: 'x-ai/grok-4.20-beta', label: 'Grok 4.20 Beta (OR)', description: "xAI's flagship model via OpenRouter.", vision: true, contextLength: 2_000_000 },
      { id: 'qwen/qwen3-max-thinking', label: 'Qwen3 Max Thinking', description: 'Flagship reasoning model in the Qwen3 series.', vision: false, reasoning: true, contextLength: 262_144 },
      { id: 'qwen/qwen3-next-80b-a3b-instruct:free', label: 'Qwen3 Next 80B A3B Instruct (Free)', description: 'Free Qwen3 Next instruct model.', vision: false, contextLength: 262_144 },
      { id: 'qwen/qwen3-coder:free', label: 'Qwen3 Coder (Free)', description: 'Free Qwen3 Coder model optimized for coding.', vision: false, contextLength: 262_144 },
      { id: 'google/gemma-4-26b-a4b-it:free', label: 'Gemma 4 26B A4B (Free)', description: 'Free Gemma 4 26B instruction-tuned model.', vision: false, contextLength: 262_144 },
      { id: 'google/gemma-4-31b-it:free', label: 'Gemma 4 31B (Free)', description: 'Free Gemma 4 31B instruction-tuned model.', vision: false, contextLength: 262_144 },
      { id: 'nvidia/nemotron-nano-9b-v2:free', label: 'Nemotron Nano 9B V2 (Free)', description: 'Free NVIDIA Nemotron Nano v2 model.', vision: false, contextLength: 128_000 },
      { id: 'minimax/minimax-m2.5:free', label: 'MiniMax M2.5 (Free)', description: 'Free MiniMax M2.5 tier on OpenRouter.', vision: false, contextLength: 196_608 },
      { id: 'z-ai/glm-4.5-air:free', label: 'GLM 4.5 Air (Free)', description: 'Free GLM 4.5 Air model by Z.ai.', vision: false, contextLength: 131_072 },
      { id: 'qwen/qwen3-coder-next', label: 'Qwen3 Coder Next', description: 'Open-weight causal LM optimised for coding.', vision: false, contextLength: 262_144 },
      { id: 'qwen/qwen3.5-9b', label: 'Qwen3.5 9B', description: 'Multimodal foundation model from the Qwen3.5 family.', vision: true, contextLength: 256_000 },
      { id: 'qwen/qwen3.5-122b-a10b', label: 'Qwen3.5 122B-A10B', description: 'Native vision-language MoE hybrid model.', vision: true, contextLength: 262_144 },
      { id: 'mistralai/mistral-small-4', label: 'Mistral Small 4', description: 'Hybrid instruct, reasoning and coding via OpenRouter.', vision: false, contextLength: 128_000 },
      { id: 'google/gemini-3.1-pro-preview', label: 'Gemini 3.1 Pro', description: 'Google flagship - complex reasoning, 1M context.', vision: true, reasoning: true, contextLength: 1_048_576 },
      { id: 'minimax/minimax-m2.7', label: 'MiniMax M2.7', description: 'Next-gen LLM for autonomous tasks, 204K context.', vision: false, contextLength: 204_800 },
      { id: 'minimax/minimax-m2.5', label: 'MiniMax M2.5', description: 'SOTA LLM for real-world productivity.', vision: false, contextLength: 197_000 },
      { id: 'nvidia/nemotron-3-super-120b-a12b', label: 'Nemotron 3 Super', description: 'NVIDIA 120B-param open hybrid Mamba-Transformer MoE model.', vision: false, contextLength: 1_000_000 },
      { id: 'nvidia/nemotron-3-super-120b-a12b:free', label: 'Nemotron 3 Super (free)', description: 'Free tier of NVIDIA Nemotron 3 Super - 1M context.', vision: false, contextLength: 1_000_000 },
      { id: 'z-ai/glm-5-turbo', label: 'GLM 5 Turbo', description: 'Fast inference and strong performance by Z.ai.', vision: false, contextLength: 200_000 },
      { id: 'z-ai/glm-5', label: 'GLM 5', description: "Z.ai's flagship open-source foundation model.", vision: false, contextLength: 200_000 },
      { id: 'bytedance-seed/seed-2.0-lite', label: 'Seed-2.0-Lite', description: 'Versatile, cost-efficient enterprise workhorse by ByteDance.', vision: false, contextLength: 262_144 },
      { id: 'xiaomi/mimo-v2-omni', label: 'MiMo-V2-Omni', description: 'Frontier omni-modal model by Xiaomi - processes image, video, audio.', vision: true, contextLength: 262_144 },
      { id: 'xiaomi/mimo-v2-pro', label: 'MiMo-V2-Pro', description: "Xiaomi's flagship 1T+ parameter foundation model.", vision: true, contextLength: 1_000_000 },
    ],
  },
]

// ── Lookup helpers ─────────────────────────────────────────────────

export function providerById(id: string): ProviderInfo | undefined {
  return PROVIDERS.find((p) => p.id === id)
}

export function providerForModel(modelId: string): ProviderInfo | undefined {
  return PROVIDERS.find((p) => p.models.some((m) => m.id === modelId))
}

export function modelInfo(modelId: string): ModelInfo | undefined {
  for (const p of PROVIDERS) {
    const m = p.models.find((m) => m.id === modelId)
    if (m) return m
  }
  return undefined
}

export function contextLengthForModel(modelId: string): number {
  for (const p of PROVIDERS) {
    const m = p.models.find((m) => m.id === modelId)
    if (m) return m.contextLength
  }
  return 128_000 // safe default
}

export function reasoningModesForModel(modelId: string): Array<'medium' | 'high' | 'extended' | 'adaptive'> {
  const model = modelInfo(modelId)
  if (!model?.reasoning) return []
  if (model.reasoningModes?.length) return model.reasoningModes
  const id = modelId.toLowerCase()
  if (id.includes('gpt-5') || id.startsWith('o3') || id.startsWith('o4')) {
    return ['medium', 'high', 'adaptive']
  }
  if (id.includes('gemini') || id.includes('claude') || id.includes('qwen')) {
    return ['medium', 'high', 'extended']
  }
  return ['medium', 'high']
}

export function allModelIds(): string[] {
  return PROVIDERS.flatMap((p) => p.models.map((m) => m.id))
}

// ── Legacy flat exports (backward compat) ──────────────────────────

export const MODEL_DESCRIPTIONS: Record<string, string> = Object.fromEntries(
  PROVIDERS.flatMap((p) => p.models.map((m) => [m.id, m.description])),
)

export const MODEL_OPTIONS = allModelIds()

/**
 * Render a provider icon that blends with dark backgrounds.
 * Icons are clipped to circles and darkened slightly so they sit
 * naturally on dark surfaces without jarring light backgrounds.
 */
export function renderProviderIcon(provider: ProviderInfo, className = 'h-4 w-4') {
  return createElement('img', {
    src: provider.iconUrl,
    alt: provider.displayName,
    className: `${className} rounded-full object-cover`,
    style: { filter: 'brightness(0.85) saturate(1.2)' },
    'aria-hidden': 'true',
  })
}
