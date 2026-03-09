import { useCallback, useEffect, useRef, useState } from 'react'

export type SteeringMode = 'steer' | 'interrupt' | 'queue'
export type TaskStatus = 'in_progress' | 'completed' | 'failed' | 'steered'

export type LogEntry = {
  id: string
  taskId: string
  message: string
  timestamp: string
  type: 'step' | 'result' | 'error' | 'interrupt'
  status: TaskStatus
  stepKind: 'analyze' | 'click' | 'type' | 'scroll' | 'navigate' | 'other'
  elapsedSeconds: number

export type LogEntry = {
  id: string
  message: string
  timestamp: string
  type: 'step' | 'result' | 'error' | 'interrupt'
}

type WebSocketPayload = {
  type: string
  data?: Record<string, unknown>
}

const guessStepKind = (message: string): LogEntry['stepKind'] => {
  const lowerMessage = message.toLowerCase()
  if (lowerMessage.includes('analy')) return 'analyze'
  if (lowerMessage.includes('click')) return 'click'
  if (lowerMessage.includes('type')) return 'type'
  if (lowerMessage.includes('scroll')) return 'scroll'
  if (lowerMessage.includes('navigat') || lowerMessage.includes('url') || lowerMessage.includes('http')) return 'navigate'
  return 'other'
}

export function useWebSocket() {
  const [connectionStatus, setConnectionStatus] = useState<'connecting' | 'connected' | 'disconnected'>('connecting')
  const [isWorking, setIsWorking] = useState<boolean>(false)
  const [latestFrame, setLatestFrame] = useState<string>('')
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [currentUrl, setCurrentUrl] = useState<string>('about:blank')
  const [activeTaskId, setActiveTaskId] = useState<string>('idle')
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectRef = useRef<number | null>(null)
  const lastStepAtRef = useRef<number>(performance.now())

  const appendLog = useCallback((entry: Omit<LogEntry, 'id' | 'timestamp' | 'elapsedSeconds' | 'stepKind'> & { elapsedSeconds?: number; stepKind?: LogEntry['stepKind'] }) => {
    const now = performance.now()
    const elapsedSeconds = entry.elapsedSeconds ?? (now - lastStepAtRef.current) / 1000
    lastStepAtRef.current = now

  const wsRef = useRef<WebSocket | null>(null)
  const reconnectRef = useRef<number | null>(null)

  const appendLog = useCallback((entry: Omit<LogEntry, 'id' | 'timestamp'>) => {
    setLogs((prev) => [
      ...prev,
      {
        ...entry,
        stepKind: entry.stepKind ?? guessStepKind(entry.message),
        elapsedSeconds,
        id: crypto.randomUUID(),
        timestamp: new Date().toLocaleTimeString(),
      },
    ])
  }, [])

  const connect = useCallback(() => {
    setConnectionStatus('connecting')
    const ws = new WebSocket(`${window.location.origin.replace('http', 'ws')}/ws/navigate`)
    wsRef.current = ws

    ws.onopen = () => setConnectionStatus('connected')
    ws.onclose = () => {
      setConnectionStatus('disconnected')
      setIsWorking(false)
      if (shouldReconnectRef.current) {
        reconnectRef.current = window.setTimeout(connect, 1500)
      }
      reconnectRef.current = window.setTimeout(connect, 1500)
    }
    ws.onerror = () => setConnectionStatus('disconnected')
    ws.onmessage = (event: MessageEvent<string>) => {
      const payload = JSON.parse(event.data) as WebSocketPayload
      const currentTaskId = activeTaskIdRef.current
      if (payload.type === 'step') {
        setIsWorking(true)
        const content = String(payload.data?.content ?? payload.data?.type ?? 'Step update')
        const urlMatch = content.match(/https?:\/\/[^\s)]+/)
        if (urlMatch?.[0]) {
          setCurrentUrl(urlMatch[0])
        }
        appendLog({
          message: content,
          type: payload.data?.type === 'interrupt' ? 'interrupt' : 'step',
          status: payload.data?.type === 'steer' ? 'steered' : 'in_progress',
          taskId: currentTaskId,
          taskId: activeTaskId,
        })
      } else if (payload.type === 'result') {
        setIsWorking(false)
        const status = String(payload.data?.status ?? 'completed')
        const failed = status !== 'completed' && status !== 'interrupted'
        appendLog({
          message: `Task ${status}`,
          type: status === 'interrupted' ? 'interrupt' : failed ? 'error' : 'result',
          status: failed ? 'failed' : 'completed',
          taskId: currentTaskId,
        })
          taskId: activeTaskId,
        })
        appendLog({ message: content, type: 'step' })
      } else if (payload.type === 'result') {
        setIsWorking(false)
        const status = String(payload.data?.status ?? 'completed')
        appendLog({ message: `Task ${status}`, type: status === 'interrupted' ? 'interrupt' : 'result' })
      } else if (payload.type === 'frame') {
        const frame = String(payload.data?.image ?? '')
        if (frame) {
          setLatestFrame(`data:image/png;base64,${frame}`)
        }
      } else if (payload.type === 'error') {
        setIsWorking(false)
        appendLog({ message: String(payload.data?.message ?? 'Unknown error'), type: 'error', status: 'failed', taskId: activeTaskId })
      }
    }
  }, [activeTaskId, appendLog])
        appendLog({ message: String(payload.data?.message ?? 'Unknown error'), type: 'error' })
      }
    }
  }, [appendLog])

  useEffect(() => {
    shouldReconnectRef.current = true
    connect()
    return () => {
      shouldReconnectRef.current = false
    connect()
    return () => {
      if (reconnectRef.current !== null) {
        window.clearTimeout(reconnectRef.current)
      }
      wsRef.current?.close()
    }
  }, [connect])

  const send = useCallback(
    (message: Record<string, unknown>) => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        if (message.action === 'navigate' || message.action === 'interrupt') {
          const nextTaskId = crypto.randomUUID()
          activeTaskIdRef.current = nextTaskId
          setActiveTaskId(nextTaskId)
          appendLog({
            message: String(message.instruction ?? 'New task'),
            type: 'step',
            status: 'in_progress',
            taskId: nextTaskId,
            stepKind: 'navigate',
            elapsedSeconds: 0,
          })
          const maybeUrl = String(message.instruction ?? '')
          if (/^https?:\/\//i.test(maybeUrl)) {
            setCurrentUrl(maybeUrl)
          }
        }
        wsRef.current.send(JSON.stringify(message))
        return true
      }
      appendLog({ message: 'WebSocket not connected', type: 'error', status: 'failed', taskId: activeTaskId })
      return false
    },
    [activeTaskId, appendLog],
  )

  const resetClientState = useCallback(() => {
    setLogs([])
    setLatestFrame('')
    setCurrentUrl('about:blank')
    setIsWorking(false)
    setActiveTaskId('idle')
  }, [])
  const send = useCallback((message: Record<string, unknown>) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(message))
      return true
    }
    appendLog({ message: 'WebSocket not connected', type: 'error' })
    return false
  }, [appendLog])

  return {
    connectionStatus,
    isWorking,
    latestFrame,
    logs,
    currentUrl,
    send,
    resetClientState,
    send,
    setLogs,
  }
}
