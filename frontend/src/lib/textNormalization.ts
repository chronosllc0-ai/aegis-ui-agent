const CONTROL_CHARS = /[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F]/g

function splitByCodeFences(text: string): Array<{ isCode: boolean; content: string }> {
  const fence = '```'
  const parts: Array<{ isCode: boolean; content: string }> = []
  let index = 0
  let insideCode = false
  while (index < text.length) {
    const fenceIndex = text.indexOf(fence, index)
    if (fenceIndex < 0) {
      parts.push({ isCode: insideCode, content: text.slice(index) })
      break
    }
    if (fenceIndex > index) {
      parts.push({ isCode: insideCode, content: text.slice(index, fenceIndex) })
    }
    parts.push({ isCode: insideCode, content: fence })
    insideCode = !insideCode
    index = fenceIndex + fence.length
  }
  return parts.length ? parts : [{ isCode: false, content: '' }]
}

function normalizeNonCodeSegment(text: string): string {
  return text
    .replace(/\r\n/g, '\n')
    .replace(/\r/g, '\n')
    .replace(/\\r\\n/g, '\n')
    .replace(/\\n/g, '\n')
    .replace(/\\r/g, '\n')
    .replace(CONTROL_CHARS, '')
}

export function normalizeTextPreservingMarkdown(text: string): string {
  const segments = splitByCodeFences(text)
  return segments
    .map((segment) => {
      if (segment.content === '```') return segment.content
      if (segment.isCode) {
        return segment.content.replace(/\r\n/g, '\n').replace(/\r/g, '\n').replace(CONTROL_CHARS, '')
      }
      return normalizeNonCodeSegment(segment.content)
    })
    .join('')
}

export class IncrementalTextNormalizer {
  private raw = ''

  push(chunk: string): string {
    this.raw += chunk
    return normalizeTextPreservingMarkdown(this.raw)
  }

  finalize(): string {
    return normalizeTextPreservingMarkdown(this.raw)
  }
}
