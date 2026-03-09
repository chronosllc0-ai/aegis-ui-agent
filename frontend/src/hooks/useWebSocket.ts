import { useCallback, useEffect, useRef, useState } from 'react'

export type SteeringMode = 'steer' | 'interrupt' | 'queue'

export type LogEntry = {
  id: string
  message: string
  type: 'step' | 'result' | 'error' | 'interrupt'
  timestamp: string
  status: 'in_progress' | 'completed' | 'failed' | 'steered'
}

export type WorkflowStep = {
  step_id: string
  parent_step_id: string | null
  action: string
  description: string
  status: 'in_progress' | 'completed' | 'failed' | 'steered'
  timestamp: string
  duration_ms: number
  screenshot: string | null
}

type WebSocketPayload = {
  type: 'step' | 'result' | 'frame' | 'error' | 'workflow_step'
  data?: Record<string, unknown>
}

export function useWebSocket() {
  const [connectionStatus, setConnectionStatus] = useState<'connecting' | 'connected' | 'disconnected'>('connecting')
  const [isWorking, setIsWorking] = useState(false)
  const [latestFrame, setLatestFrame] = useState('')
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [workflowSteps, setWorkflowSteps] = useState<WorkflowStep[]>([])
  const wsRef = useRef<WebSocket | null>(null)

  const appendLog = useCallback((entry: Omit<LogEntry, 'id' | 'timestamp'>) => {
    setLogs((prev) => [...prev, { ...entry, id: crypto.randomUUID(), timestamp: new Date().toLocaleTimeString() }])
  }, [])

  useEffect(() => {
    const connect = () => {
      const ws = new WebSocket(`${window.location.origin.replace('http', 'ws')}/ws/navigate`)
      wsRef.current = ws
      setConnectionStatus('connecting')

      ws.onopen = () => setConnectionStatus('connected')
      ws.onclose = () => {
        setConnectionStatus('disconnected')
        setIsWorking(false)
        window.setTimeout(connect, 1500)
      }
      ws.onerror = () => setConnectionStatus('disconnected')
      ws.onmessage = (event: MessageEvent<string>) => {
        const payload = JSON.parse(event.data) as WebSocketPayload
        if (payload.type === 'step') {
          setIsWorking(true)
          appendLog({
            message: String(payload.data?.content ?? 'Step update'),
            type: payload.data?.type === 'interrupt' ? 'interrupt' : 'step',
            status: payload.data?.type === 'steer' ? 'steered' : 'in_progress',
          })
          return
        }
        if (payload.type === 'result') {
          setIsWorking(false)
          const status = String(payload.data?.status ?? 'completed')
          appendLog({
            message: `Task ${status}`,
            type: status === 'interrupted' ? 'interrupt' : 'result',
            status: status === 'completed' ? 'completed' : status === 'interrupted' ? 'steered' : 'failed',
          })
          return
        }
        if (payload.type === 'frame') {
          const frame = String(payload.data?.image ?? '')
          if (frame) setLatestFrame(`data:image/png;base64,${frame}`)
          return
        }
        if (payload.type === 'workflow_step') {
          const step = payload.data as unknown as WorkflowStep
          setWorkflowSteps((prev) => [...prev.filter((item) => item.step_id !== step.step_id), step])
          return
        }
        if (payload.type === 'error') {
          setIsWorking(false)
          appendLog({ message: String(payload.data?.message ?? 'Unknown error'), type: 'error', status: 'failed' })
        }
      }
    }

    connect()
    return () => wsRef.current?.close()
  }, [appendLog])

  const send = useCallback((message: Record<string, unknown>) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(message))
      return true
    }
    appendLog({ message: 'WebSocket not connected', type: 'error', status: 'failed' })
    return false
  }, [appendLog])

  return { connectionStatus, isWorking, latestFrame, logs, workflowSteps, send, setLogs, setWorkflowSteps }
}
