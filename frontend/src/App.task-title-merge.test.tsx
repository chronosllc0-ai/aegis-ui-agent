import { describe, expect, it } from 'vitest'

import { mergeTitlePreferMeaningful } from './lib/title'

describe('App task title merge behavior', () => {
  it('keeps richer local title while server sends placeholder, then switches when promoted title arrives', () => {
    const localTitle = 'Find wireless headphones under $50'

    const afterPlaceholderSync = mergeTitlePreferMeaningful(
      localTitle,
      'New task',
      localTitle,
    )
    expect(afterPlaceholderSync).toBe(localTitle)

    const afterPromotedSync = mergeTitlePreferMeaningful(
      afterPlaceholderSync,
      'Find wireless headphones under $50 and free shipping',
      localTitle,
    )
    expect(afterPromotedSync).toBe('Find wireless headphones under $50 and free shipping')
  })

  it('promotes from placeholder to derived local candidate once and remains stable through placeholder refreshes', () => {
    const candidate = 'Compare laptop deals this weekend'
    const titlesSeen: string[] = []

    let title = mergeTitlePreferMeaningful('New task', 'New task', candidate)
    titlesSeen.push(title)

    title = mergeTitlePreferMeaningful(title, 'New task', candidate)
    titlesSeen.push(title)

    title = mergeTitlePreferMeaningful(title, 'Compare laptop deals this weekend with coupons', candidate)
    titlesSeen.push(title)

    expect(titlesSeen[0]).toBe(candidate)
    expect(titlesSeen[1]).toBe(candidate)
    expect(titlesSeen[2]).toBe('Compare laptop deals this weekend with coupons')
  })
})
