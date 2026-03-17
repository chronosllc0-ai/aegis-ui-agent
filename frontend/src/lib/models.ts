// ── Provider + Model catalogue ───────────────────────────────────────

export type ProviderInfo = {
  id: string
  displayName: string
  models: string[]
  icon: string
  keyPrefix: string
}

export const PROVIDERS: ProviderInfo[] = [
  {
    id: 'google',
    displayName: 'Google (Gemini)',
    models: [
      'gemini-2.5-pro',
      'gemini-2.5-flash',
      'gemini-3-pro',
      'gemini-3.1-pro-preview',
      'gemini-3.1-flash-lite-preview',
      'gemini-3-flash-preview',
      'gemini-3-pro-preview',
    ],
    icon: 'https://i.postimg.cc/NMtZmLXT/download_4.png',
    keyPrefix: '',
  },
  {
    id: 'openai',
    displayName: 'OpenAI',
    models: ['gpt-4.1', 'gpt-4.1-mini', 'gpt-4.1-nano', 'o4-mini', 'o3', 'o3-mini', 'gpt-4o', 'gpt-4o-mini'],
    icon: '🤖',
    keyPrefix: 'sk-',
  },
  {
    id: 'anthropic',
    displayName: 'Anthropic',
    models: [
      'claude-sonnet-4-20250514',
      'claude-3.5-sonnet-20241022',
      'claude-3.5-haiku-20241022',
      'claude-3-opus-20240229',
    ],
    icon: '🧠',
    keyPrefix: 'sk-ant-',
  },
  {
    id: 'mistral',
    displayName: 'Mistral AI',
    models: [
      'mistral-large-latest',
      'mistral-medium-latest',
      'mistral-small-latest',
      'codestral-latest',
      'pixtral-large-latest',
    ],
    icon: '🌀',
    keyPrefix: '',
  },
  {
    id: 'groq',
    displayName: 'Groq',
    models: [
      'llama-3.3-70b-versatile',
      'llama-3.1-8b-instant',
      'mixtral-8x7b-32768',
      'gemma2-9b-it',
      'deepseek-r1-distill-llama-70b',
    ],
    icon: '⚡',
    keyPrefix: 'gsk_',
  },
]

export function providerForModel(model: string): ProviderInfo | undefined {
  return PROVIDERS.find((p) => p.models.includes(model))
}

export function allModels(): string[] {
  return PROVIDERS.flatMap((p) => p.models)
}

// Flat descriptions kept for backward compat in AgentTab
export const MODEL_DESCRIPTIONS: Record<string, string> = {
  // Google
  'gemini-2.5-pro': 'Gemini 2.5 Pro — best quality and complex reasoning.',
  'gemini-2.5-flash': 'Gemini 2.5 Flash — fast responses, lower latency.',
  'gemini-3-pro': 'Gemini 3 Pro — latest multimodal flagship.',
  'gemini-3.1-pro-preview': 'Gemini 3.1 Pro preview — cutting-edge reasoning.',
  'gemini-3.1-flash-lite-preview': 'Gemini 3.1 Flash Lite — ultra-low latency.',
  'gemini-3-flash-preview': 'Gemini 3 Flash preview — fast navigation.',
  'gemini-3-pro-preview': 'Gemini 3 Pro preview — high-quality multimodal.',
  // OpenAI
  'gpt-4.1': 'GPT-4.1 — flagship model, best overall quality.',
  'gpt-4.1-mini': 'GPT-4.1 Mini — fast and cost-effective.',
  'gpt-4.1-nano': 'GPT-4.1 Nano — ultra-lightweight.',
  'o4-mini': 'o4-mini — advanced reasoning, compact.',
  'o3': 'o3 — deep reasoning model.',
  'o3-mini': 'o3-mini — efficient reasoning.',
  'gpt-4o': 'GPT-4o — multimodal with vision.',
  'gpt-4o-mini': 'GPT-4o Mini — fast multimodal.',
  // Anthropic
  'claude-sonnet-4-20250514': 'Claude Sonnet 4 — latest balanced model.',
  'claude-3.5-sonnet-20241022': 'Claude 3.5 Sonnet — excellent code & reasoning.',
  'claude-3.5-haiku-20241022': 'Claude 3.5 Haiku — fastest Anthropic model.',
  'claude-3-opus-20240229': 'Claude 3 Opus — maximum capability.',
  // Mistral
  'mistral-large-latest': 'Mistral Large — top-tier multilingual.',
  'mistral-medium-latest': 'Mistral Medium — balanced performance.',
  'mistral-small-latest': 'Mistral Small — fast and efficient.',
  'codestral-latest': 'Codestral — optimized for code.',
  'pixtral-large-latest': 'Pixtral Large — multimodal vision.',
  // Groq
  'llama-3.3-70b-versatile': 'Llama 3.3 70B — fast open-source on Groq.',
  'llama-3.1-8b-instant': 'Llama 3.1 8B — ultra-low latency.',
  'mixtral-8x7b-32768': 'Mixtral 8x7B — 32K context mixture-of-experts.',
  'gemma2-9b-it': 'Gemma 2 9B — Google open model on Groq.',
  'deepseek-r1-distill-llama-70b': 'DeepSeek R1 Distill — reasoning model on Groq.',
}

export const MODEL_OPTIONS = Object.keys(MODEL_DESCRIPTIONS)

export const MODEL_ICON_URL = 'https://i.postimg.cc/NMtZmLXT/download_4.png'
