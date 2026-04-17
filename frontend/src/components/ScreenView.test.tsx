import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { ScreenView } from './ScreenView'

describe('ScreenView HITL browser actions', () => {
  it('only emits human actions when handoffActive=true', async () => {
    const onHumanBrowserAction = vi.fn()
    const { rerender } = render(
      <ScreenView
        frameSrc='data:image/png;base64,abc'
        isWorking
        steeringFlashKey={0}
        onExampleClick={vi.fn()}
        handoffActive={false}
        onHumanBrowserAction={onHumanBrowserAction}
      />,
    )

    const image = await screen.findByAltText('Live browser stream')
    const overlay = image.parentElement as HTMLDivElement
    Object.defineProperty(overlay, 'getBoundingClientRect', {
      configurable: true,
      value: () => ({ left: 0, top: 0, width: 1280, height: 720, right: 1280, bottom: 720, x: 0, y: 0, toJSON: () => ({}) }),
    })

    fireEvent.click(overlay, { clientX: 100, clientY: 120 })
    fireEvent.wheel(overlay, { deltaY: 90 })
    fireEvent.keyDown(overlay, { key: 'a' })
    expect(onHumanBrowserAction).not.toHaveBeenCalled()

    rerender(
      <ScreenView
        frameSrc='data:image/png;base64,abc'
        isWorking
        steeringFlashKey={0}
        onExampleClick={vi.fn()}
        handoffActive
        onHumanBrowserAction={onHumanBrowserAction}
      />,
    )

    const activeOverlay = (await screen.findByAltText('Live browser stream')).parentElement as HTMLDivElement

    fireEvent.click(activeOverlay, { clientX: 100, clientY: 120 })
    fireEvent.wheel(activeOverlay, { deltaY: 90 })
    fireEvent.keyDown(activeOverlay, { key: 'Enter' })

    expect(onHumanBrowserAction).toHaveBeenNthCalledWith(1, { kind: 'click', x: 100, y: 120 })
    expect(onHumanBrowserAction).toHaveBeenNthCalledWith(2, { kind: 'scroll', deltaY: 90 })
    expect(onHumanBrowserAction).toHaveBeenNthCalledWith(3, { kind: 'press_key', key: 'Enter' })
  })
})
