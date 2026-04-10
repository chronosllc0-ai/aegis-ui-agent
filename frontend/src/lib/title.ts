export const PLACEHOLDER_TITLES = new Set(['new task', 'new web conversation', 'untitled', ''])

export const normalizeTitle = (t?: string | null): string => (t ?? '').trim()

export const isPlaceholderTitle = (t?: string | null): boolean =>
  PLACEHOLDER_TITLES.has(normalizeTitle(t).toLowerCase())

export const deriveTitleFromInstruction = (text?: string | null, limit = 120): string => {
  const clean = (text ?? '').split(/\s+/).filter(Boolean).join(' ').trim()
  return (clean || 'New task').slice(0, limit)
}

export const mergeTitlePreferMeaningful = (
  localTitle?: string | null,
  serverTitle?: string | null,
  fallbackCandidate?: string | null,
): string => {
  const local = normalizeTitle(localTitle)
  const server = normalizeTitle(serverTitle)

  if (!isPlaceholderTitle(server)) return server
  if (!isPlaceholderTitle(local)) return local
  return deriveTitleFromInstruction(fallbackCandidate)
}
