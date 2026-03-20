// ── Provider + Model catalogue ───────────────────────────────────────
// Last updated: 2026-03-18 — sourced from official provider docs

import { createElement } from 'react'

// ── Provider icon URLs (hosted on postimg) ────────────────────────
export const PROVIDER_ICON_URLS: Record<string, string> = {
  google:    'https://i.postimg.cc/2SwWrKwz/download_1.jpg',
  openai:    'https://i.postimg.cc/d3HRsSv7/download_2.png',
  anthropic: 'https://i.postimg.cc/L6yVy6b3/2eb79382ad63416682dcc08c91fcc46f.png',
  mistral:   'https://i.postimg.cc/mgvCqcNP/mistral-ai-icon-logo-png-seeklogo-515008.png',
  groq:      'https://i.postimg.cc/hjFSTn8V/download_7.png',
}

// Chronos AI logo
export const CHRONOS_LOGO_URL = 'https://i.postimg.cc/c1zHTpc3/IMG-20260103-192235-443.webp'

export type ModelInfo = {
  id: string
  label: string
  description: string
  vision?: boolean
  contextLength: number  // max context window in tokens
}

export type ProviderInfo = {
  id: string
  displayName: string
  models: ModelInfo[]
  iconUrl: string
  keyPrefix: string
}

export const PROVIDERS: ProviderInfo[] = [
  // ── Google ──────────────────────────────────────────────────────────
  {
    id: 'google',
    displayName: 'Google (Gemini)',
    iconUrl: PROVIDER_ICON_URLS.google,
    keyPrefix: '',
    models: [
      { id: 'gemini-3.1-pro-preview', label: 'Gemini 3.1 Pro Preview', description: 'Latest Gemini 3 series — cutting-edge reasoning & multimodal.', vision: true, contextLength: 2_000_000 },
      { id: 'gemini-3.1-flash-lite-preview', label: 'Gemini 3.1 Flash-Lite Preview', description: 'First Flash-Lite in the Gemini 3 series — ultra-fast.', vision: true, contextLength: 1_000_000 },
      { id: 'gemini-3-flash-preview', label: 'Gemini 3 Flash Preview', description: 'Frontier-class speed that rivals larger models.', vision: true, contextLength: 1_000_000 },
      { id: 'gemini-2.5-pro', label: 'Gemini 2.5 Pro', description: 'Stable production model — best quality + complex reasoning.', vision: true, contextLength: 1_048_576 },
      { id: 'gemini-2.5-flash', label: 'Gemini 2.5 Flash', description: 'Stable production model — fast responses, lower latency.', vision: true, contextLength: 1_048_576 },
    ],
  },
  // ── OpenAI ──────────────────────────────────────────────────────────
  {
    id: 'openai',
    displayName: 'OpenAI',
    iconUrl: PROVIDER_ICON_URLS.openai,
    keyPrefix: 'sk-',
    models: [
      { id: 'gpt-5.2', label: 'GPT-5.2', description: 'Flagship — best for coding and agentic tasks.', vision: true, contextLength: 256_000 },
      { id: 'gpt-5.2-pro', label: 'GPT-5.2 Pro', description: 'Smarter, more precise responses on complex tasks.', vision: true, contextLength: 256_000 },
      { id: 'gpt-5', label: 'GPT-5', description: 'Intelligent reasoning model with configurable effort.', vision: true, contextLength: 256_000 },
      { id: 'gpt-5-mini', label: 'GPT-5 Mini', description: 'Fast, cost-efficient version of GPT-5.', vision: true, contextLength: 256_000 },
      { id: 'gpt-5-nano', label: 'GPT-5 Nano', description: 'Fastest, most cost-efficient GPT-5 variant.', vision: true, contextLength: 128_000 },
      { id: 'gpt-4.1', label: 'GPT-4.1', description: 'Smartest non-reasoning model.', vision: true, contextLength: 1_047_576 },
      { id: 'gpt-4.1-mini', label: 'GPT-4.1 Mini', description: 'Fast and cost-effective.', vision: true, contextLength: 1_047_576 },
      { id: 'gpt-4.1-nano', label: 'GPT-4.1 Nano', description: 'Ultra-lightweight.', vision: true, contextLength: 1_047_576 },
      { id: 'o4-mini', label: 'o4-mini', description: 'Advanced reasoning, compact.', vision: true, contextLength: 200_000 },
      { id: 'o3', label: 'o3', description: 'Deep reasoning model.', vision: true, contextLength: 200_000 },
    ],
  },
  // ── Anthropic ───────────────────────────────────────────────────────
  {
    id: 'anthropic',
    displayName: 'Anthropic',
    iconUrl: PROVIDER_ICON_URLS.anthropic,
    keyPrefix: 'sk-ant-',
    models: [
      { id: 'claude-opus-4-6', label: 'Claude Opus 4.6', description: 'Most intelligent — agents and coding. 1M context.', vision: true, contextLength: 1_000_000 },
      { id: 'claude-sonnet-4-6', label: 'Claude Sonnet 4.6', description: 'Best combo of speed + intelligence. 1M context.', vision: true, contextLength: 1_000_000 },
      { id: 'claude-haiku-4-5', label: 'Claude Haiku 4.5', description: 'Fastest Anthropic model — near-frontier intelligence.', vision: true, contextLength: 200_000 },
      { id: 'claude-sonnet-4-20250514', label: 'Claude Sonnet 4', description: 'Previous generation balanced model.', vision: true, contextLength: 200_000 },
      { id: 'claude-3.5-sonnet-20241022', label: 'Claude 3.5 Sonnet', description: 'Excellent code and reasoning.', vision: true, contextLength: 200_000 },
    ],
  },
  // ── Mistral ─────────────────────────────────────────────────────────
  {
    id: 'mistral',
    displayName: 'Mistral AI',
    iconUrl: PROVIDER_ICON_URLS.mistral,
    keyPrefix: '',
    models: [
      { id: 'mistral-large-latest', label: 'Mistral Large 3', description: 'State-of-the-art open-weight multimodal model.', vision: true, contextLength: 128_000 },
      { id: 'mistral-medium-latest', label: 'Mistral Medium 3.1', description: 'Frontier-class multimodal — Aug 2025.', vision: true, contextLength: 128_000 },
      { id: 'mistral-small-latest', label: 'Mistral Small 4', description: 'Hybrid instruct, reasoning, and coding.', vision: false, contextLength: 128_000 },
      { id: 'codestral-latest', label: 'Codestral', description: 'Optimized for code generation.', vision: false, contextLength: 256_000 },
      { id: 'pixtral-large-latest', label: 'Pixtral Large', description: 'Multimodal vision model.', vision: true, contextLength: 128_000 },
      { id: 'devstral-small-2505', label: 'Devstral Small', description: 'Developer-focused small model.', vision: false, contextLength: 128_000 },
    ],
  },
  // ── Groq ────────────────────────────────────────────────────────────
  {
    id: 'groq',
    displayName: 'Groq',
    iconUrl: PROVIDER_ICON_URLS.groq,
    keyPrefix: 'gsk_',
    models: [
      { id: 'meta-llama/llama-4-scout-17b-16e-instruct', label: 'Llama 4 Scout 17B', description: 'Llama 4 on Groq — fast multimodal inference.', vision: true, contextLength: 512_000 },
      { id: 'llama-3.3-70b-versatile', label: 'Llama 3.3 70B', description: 'Fast open-source on Groq.', vision: false, contextLength: 128_000 },
      { id: 'llama-3.1-8b-instant', label: 'Llama 3.1 8B', description: 'Ultra-low latency.', vision: false, contextLength: 131_072 },
      { id: 'openai/gpt-oss-120b', label: 'GPT-OSS 120B', description: 'OpenAI open-weight model on Groq LPU.', vision: false, contextLength: 128_000 },
      { id: 'openai/gpt-oss-20b', label: 'GPT-OSS 20B', description: 'Medium open-weight, extreme speed.', vision: false, contextLength: 128_000 },
      { id: 'moonshotai/kimi-k2-instruct-0905', label: 'Kimi K2', description: 'Moonshot K2 — strong reasoning on Groq.', vision: false, contextLength: 128_000 },
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

export function allModelIds(): string[] {
  return PROVIDERS.flatMap((p) => p.models.map((m) => m.id))
}

// ── Legacy flat exports (backward compat) ──────────────────────────

export const MODEL_DESCRIPTIONS: Record<string, string> = Object.fromEntries(
  PROVIDERS.flatMap((p) => p.models.map((m) => [m.id, m.description])),
)

export const MODEL_OPTIONS = allModelIds()

export const MODEL_ICON_URL = 'https://i.postimg.cc/NMtZmLXT/download_4.png'

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
