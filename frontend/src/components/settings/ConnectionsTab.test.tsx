import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ConnectionsTab } from './ConnectionsTab'

const baseIntegrations = [
  { id: 'web-search', name: 'Web Search', icon: 'web-search', description: 'd', enabled: false, status: 'disabled', builtIn: true, tools: [] },
] as const

describe('ConnectionsTab MCP + admin wizard', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.includes('/api/mcp/presets')) {
        return new Response(JSON.stringify({ ok: true, presets: [{ id: 'preset-browsermcp', name: 'BrowserMCP', description: 'Browser preset', user_status: 'not_added' }] }), { status: 200 })
      }
      if (url.includes('/api/connectors')) {
        return new Response(JSON.stringify({ ok: true, connectors: [] }), { status: 200 })
      }
      if (url.includes('/api/mcp/servers') && !url.includes('/scan') && init?.method !== 'POST') {
        return new Response(JSON.stringify({ ok: true, servers: [] }), { status: 200 })
      }
      if (url.includes('/api/mcp/servers/custom')) {
        return new Response(JSON.stringify({ ok: true, server: { id: 'custom-1', name: 'Custom 1', status: 'added' } }), { status: 200 })
      }
      if (url.includes('/api/admin/connections/test')) {
        return new Response(JSON.stringify({ ok: true, message: 'valid' }), { status: 200 })
      }
      if (url.includes('/api/admin/connections')) {
        return new Response(JSON.stringify({ ok: true, connection_id: 'draft-1', status: 'draft' }), { status: 200 })
      }
      if (url.includes('/api/mcp/servers/from-preset')) {
        return new Response(JSON.stringify({ ok: true }), { status: 200 })
      }
      return new Response(JSON.stringify({ ok: true }), { status: 200 })
    }))
  })

  it('renders MCP section above custom server block and preserves custom submit', async () => {
    const onChange = vi.fn()
    render(<ConnectionsTab integrations={[...baseIntegrations]} onChange={onChange} isAdmin={false} />)

    await waitFor(() => expect(screen.getByText('MCP')).toBeInTheDocument())

    const mcpHeading = screen.getByRole('heading', { name: 'MCP' })
    const customButton = screen.getByRole('button', { name: /Add Custom MCP Server/ })
    expect(mcpHeading.compareDocumentPosition(customButton) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: /Add Custom MCP Server/ }))
    fireEvent.change(screen.getByPlaceholderText('Server name'), { target: { value: 'My MCP' } })
    fireEvent.change(screen.getByPlaceholderText('Server URL (http://localhost:3000/mcp)'), { target: { value: 'http://localhost:3333/mcp' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => expect(onChange).toHaveBeenCalled())
  })

  it('shows admin New Connection buttons only for admin and supports wizard navigation', async () => {
    const onChange = vi.fn()
    const { rerender } = render(<ConnectionsTab integrations={[...baseIntegrations]} onChange={onChange} isAdmin={false} />)
    await waitFor(() => expect(screen.queryByText('+ New Connection')).not.toBeInTheDocument())

    rerender(<ConnectionsTab integrations={[...baseIntegrations]} onChange={onChange} isAdmin />)
    await waitFor(() => expect(screen.getAllByText('+ New Connection').length).toBeGreaterThan(1))

    fireEvent.click(screen.getAllByText('+ New Connection')[0])
    expect(screen.getByText('Step 1 of 5')).toBeInTheDocument()

    fireEvent.change(screen.getByPlaceholderText('Name'), { target: { value: 'Admin MCP' } })
    fireEvent.click(screen.getAllByText('Continue')[0])
    await waitFor(() => expect(screen.getByText('Step 2 of 5')).toBeInTheDocument())

    fireEvent.click(screen.getByText('mcp'))
    fireEvent.click(screen.getAllByText('Continue')[0])
    await waitFor(() => expect(screen.getByText('Step 3 of 5')).toBeInTheDocument())
  })
})
