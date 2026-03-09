import { useCallback, useEffect, useRef, useState } from 'react'

export type SteeringMode = 'steer' | 'interrupt' | 'queue'

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

export function useWebSocket() {
  const [connectionStatus, setConnectionStatus] = useState<'connecting' | 'connected' | 'disconnected'>('connecting')
  const [isWorking, setIsWorking] = useState<boolean>(false)
  const [latestFrame, setLatestFrame] = useState<string>('')
  const [logs, setLogs] = useState<LogEntry[]>([])
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectRef = useRef<number | null>(null)

  const appendLog = useCallback((entry: Omit<LogEntry, 'id' | 'timestamp'>) => {
    setLogs((prev) => [
      ...prev,
      {
        ...entry,
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
      reconnectRef.current = window.setTimeout(connect, 1500)
    }
    ws.onerror = () => setConnectionStatus('disconnected')
    ws.onmessage = (event: MessageEvent<string>) => {
      const payload = JSON.parse(event.data) as WebSocketPayload
      if (payload.type === 'step') {
        setIsWorking(true)
        const content = String(payload.data?.content ?? payload.data?.type ?? 'Step update')
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
        appendLog({ message: String(payload.data?.message ?? 'Unknown error'), type: 'error' })
      }
    }
  }, [appendLog])

  useEffect(() => {
    connect()
    return () => {
      if (reconnectRef.current !== null) {
        window.clearTimeout(reconnectRef.current)
      }
      wsRef.current?.close()
    }
  }, [connect])

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
    send,
    setLogs,
  }
}
