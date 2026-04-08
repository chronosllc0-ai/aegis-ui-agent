import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ReviewQueue } from './ReviewQueue'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('ReviewQueue risk tags', () => {
  it('renders risk badge and filter chips', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/api/skills/hub/review-queue')) {
        return {
          ok: true,
          json: async () => ({
            items: [
              {
                id: 'sub-1',
                title: 'Skill One',
                skill_slug: 'skill-one',
                current_state: 'submitted',
                risk_label: 'suspicious',
              },
            ],
          }),
        } as Response
      }
      return { ok: true, json: async () => ({}) } as Response
    }))

    render(<ReviewQueue isAdmin />)

    await waitFor(() => expect(screen.getByText('suspicious')).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: 'malicious' }))
    await waitFor(() => {
      expect((fetch as ReturnType<typeof vi.fn>).mock.calls.some((args) => String(args[0]).includes('risk_label=malicious'))).toBe(true)
    })
  })
})
