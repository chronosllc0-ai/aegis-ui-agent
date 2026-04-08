/**
 * Normalize ask_user_input options emitted by the backend/tools.
 *
 * Supports string entries (`["A", "B"]`) and object entries
 * (`[{ label: "A" }, { id: "b" }]`), trims values, and de-duplicates
 * by first appearance order.
 */
export function normalizeAskUserInputOptions(rawOptions: unknown): string[] {
  if (!Array.isArray(rawOptions)) return []

  const seen = new Set<string>()
  const normalized: string[] = []

  for (const opt of rawOptions) {
    let candidate = ''

    if (typeof opt === 'string') {
      candidate = opt.trim()
    } else if (opt && typeof opt === 'object') {
      const record = opt as Record<string, unknown>
      const label = typeof record.label === 'string' ? record.label.trim() : ''
      const fallback = typeof record.id === 'string' ? record.id.trim() : ''
      candidate = label || fallback
    }

    if (!candidate || seen.has(candidate)) continue
    seen.add(candidate)
    normalized.push(candidate)
  }

  return normalized
}
