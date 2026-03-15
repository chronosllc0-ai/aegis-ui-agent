import { useCallback, useEffect, useRef, useState } from 'react'

export type SteeringMode = 'steer' | 'interrupt' | 'queue'
<<<<<<< ours
=======
export type TaskStatus = 'in_progress' | 'completed' | 'failed' | 'steered'
>>>>>>> theirs

export type LogEntry = {
  id: string
  taskId: string
  message: string
<<<<<<< ours
  type: 'step' | 'result' | 'error' | 'interrupt'
  timestamp: string
  status: 'in_progress' | 'completed' | 'failed' | 'steered'
=======
  timestamp: string
  type: 'step' | 'result' | 'error' | 'interrupt'
  status: TaskStatus
>>>>>>> theirs
  stepKind: 'analyze' | 'click' | 'type' | 'scroll' | 'navigate' | 'other'
  elapsedSeconds: number
}

<<<<<<< ours
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

function guessStepKind(message: string): LogEntry['stepKind'] {
  const text = message.toLowerCase()
  if (text.includes('click')) return 'click'
  if (text.includes('type')) return 'type'
  if (text.includes('scroll')) return 'scroll'
  if (text.includes('analy')) return 'analyze'
  if (text.includes('http') || text.includes('navigate') || text.includes('open')) return 'navigate'
=======
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
>>>>>>> theirs
  return 'other'
}

export function useWebSocket() {
  const [connectionStatus, setConnectionStatus] = useState<'connecting' | 'connected' | 'disconnected'>('connecting')
<<<<<<< ours
  const [isWorking, setIsWorking] = useState(false)
  const [latestFrame, setLatestFrame] = useState('')
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [workflowSteps, setWorkflowSteps] = useState<WorkflowStep[]>([])
  const [currentUrl, setCurrentUrl] = useState('about:blank')
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectRef = useRef<number | null>(null)
  const shouldReconnectRef = useRef(true)
  const activeTaskIdRef = useRef('idle')
  const lastStepAtRef = useRef(performance.now())

  const appendLog = useCallback((entry: Omit<LogEntry, 'id' | 'timestamp' | 'elapsedSeconds' | 'stepKind'> & { elapsedSeconds?: number; stepKind?: LogEntry['stepKind'] }) => {
    const now = performance.now()
    const elapsed = entry.elapsedSeconds ?? (now - lastStepAtRef.current) / 1000
    lastStepAtRef.current = now
    setLogs((prev) => [
      ...prev,
      {
        ...entry,
        id: crypto.randomUUID(),
        timestamp: new Date().toLocaleTimeString(),
        elapsedSeconds: elapsed,
        stepKind: entry.stepKind ?? guessStepKind(entry.message),
      },
    ])
  }, [])

  const connect = useCallback(() => {
    const ws = new WebSocket(`${window.location.origin.replace('http', 'ws')}/ws/navigate`)
    wsRef.current = ws
    setConnectionStatus('connecting')
=======
  const [isWorking, setIsWorking] = useState<boolean>(false)
  const [latestFrame, setLatestFrame] = useState<string>('')
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [currentUrl, setCurrentUrl] = useState<string>('about:blank')
  const [activeTaskId, setActiveTaskId] = useState<string>('idle')
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectRef = useRef<number | null>(null)
  const shouldReconnectRef = useRef<boolean>(true)
  const activeTaskIdRef = useRef<string>('idle')
  const lastStepAtRef = useRef<number>(performance.now())

  useEffect(() => {
    activeTaskIdRef.current = activeTaskId
  }, [activeTaskId])

  const appendLog = useCallback(
    (entry: Omit<LogEntry, 'id' | 'timestamp' | 'elapsedSeconds' | 'stepKind'> & { elapsedSeconds?: number; stepKind?: LogEntry['stepKind'] }) => {
      const now = performance.now()
      const elapsedSeconds = entry.elapsedSeconds ?? (now - lastStepAtRef.current) / 1000
      lastStepAtRef.current = now

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
    },
    [],
  )

  const connect = useCallback(() => {
    setConnectionStatus('connecting')
    const configuredWsUrl = (import.meta.env.VITE_WS_URL as string | undefined)?.trim()
    const wsUrl = configuredWsUrl && configuredWsUrl.length > 0 ? configuredWsUrl : `${window.location.origin.replace('http', 'ws')}/ws/navigate`
    const ws = new WebSocket(wsUrl)
    wsRef.current = ws
>>>>>>> theirs

    ws.onopen = () => setConnectionStatus('connected')
    ws.onclose = () => {
      setConnectionStatus('disconnected')
      setIsWorking(false)
      if (shouldReconnectRef.current) {
<<<<<<< ours
        if (reconnectRef.current !== null) {
          window.clearTimeout(reconnectRef.current)
        }
        reconnectRef.current = window.setTimeout(connect, 1400)
=======
        reconnectRef.current = window.setTimeout(connect, 1500)
>>>>>>> theirs
      }
    }
    ws.onerror = () => setConnectionStatus('disconnected')
    ws.onmessage = (event: MessageEvent<string>) => {
      const payload = JSON.parse(event.data) as WebSocketPayload
<<<<<<< ours
      const taskId = activeTaskIdRef.current
      if (payload.type === 'step') {
        setIsWorking(true)
        const content = String(payload.data?.content ?? 'Step update')
        const urlMatch = content.match(/https?:\/\/[^\s)]+/)
        if (urlMatch?.[0]) setCurrentUrl(urlMatch[0])
        appendLog({
          message: content,
          taskId,
          type: payload.data?.type === 'interrupt' ? 'interrupt' : 'step',
          status: payload.data?.type === 'steer' ? 'steered' : 'in_progress',
        })
        return
      }
      if (payload.type === 'result') {
=======
      const currentTaskId = activeTaskIdRef.current
      if (payload.type === 'step') {
        const stepType = String(payload.data?.type ?? '').toLowerCase()
        const nonExecutionStepTypes = new Set(['queue', 'steer', 'config'])
        const isNonExecutionStep = nonExecutionStepTypes.has(stepType)
        if (!isNonExecutionStep) {
          setIsWorking(true)
        }

        const content = String(payload.data?.content ?? payload.data?.type ?? 'Step update')
        const urlMatch = content.match(/https?:\/\/[^\s)]+/)
        if (urlMatch?.[0]) {
          setCurrentUrl(urlMatch[0])
        }
        appendLog({
          message: content,
          type: stepType === 'interrupt' ? 'interrupt' : 'step',
          status: stepType === 'steer' ? 'steered' : 'in_progress',
          taskId: currentTaskId,
        })
      } else if (payload.type === 'result') {
>>>>>>> theirs
        setIsWorking(false)
        const status = String(payload.data?.status ?? 'completed')
        const failed = status !== 'completed' && status !== 'interrupted'
        appendLog({
          message: `Task ${status}`,
<<<<<<< ours
          taskId,
          type: status === 'interrupted' ? 'interrupt' : failed ? 'error' : 'result',
          status: failed ? 'failed' : 'completed',
        })
        return
      }
      if (payload.type === 'frame') {
        const image = String(payload.data?.image ?? '')
        if (image) setLatestFrame(`data:image/png;base64,${image}`)
        return
      }
      if (payload.type === 'workflow_step') {
        const step = payload.data as unknown as WorkflowStep
        setWorkflowSteps((prev) => [...prev.filter((item) => item.step_id !== step.step_id), step])
        return
      }
      if (payload.type === 'error') {
        setIsWorking(false)
        appendLog({ message: String(payload.data?.message ?? 'Unknown error'), taskId, type: 'error', status: 'failed' })
=======
          type: status === 'interrupted' ? 'interrupt' : failed ? 'error' : 'result',
          status: failed ? 'failed' : 'completed',
          taskId: currentTaskId,
        })
      } else if (payload.type === 'frame') {
        const frame = String(payload.data?.image ?? '')
        if (frame) {
          setLatestFrame(`data:image/png;base64,${frame}`)
        }
      } else if (payload.type === 'error') {
        setIsWorking(false)
        appendLog({ message: String(payload.data?.message ?? 'Unknown error'), type: 'error', status: 'failed', taskId: currentTaskId })
>>>>>>> theirs
      }
    }
  }, [appendLog])

  useEffect(() => {
<<<<<<< ours
=======
    shouldReconnectRef.current = true
>>>>>>> theirs
    connect()
    return () => {
      shouldReconnectRef.current = false
      if (reconnectRef.current !== null) {
        window.clearTimeout(reconnectRef.current)
<<<<<<< ours
        reconnectRef.current = null
      }
      if (wsRef.current) {
        wsRef.current.onclose = null
        wsRef.current.close()
      }
    }
  }, [connect])

  const send = useCallback((message: Record<string, unknown>) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      if (message.action === 'navigate' || message.action === 'interrupt') {
        const nextTaskId = crypto.randomUUID()
        activeTaskIdRef.current = nextTaskId
        appendLog({ message: String(message.instruction ?? 'New task'), taskId: nextTaskId, type: 'step', status: 'in_progress', stepKind: 'navigate', elapsedSeconds: 0 })
        const maybeUrl = String(message.instruction ?? '')
        if (/^https?:\/\//i.test(maybeUrl)) setCurrentUrl(maybeUrl)
      }
      wsRef.current.send(JSON.stringify(message))
      return true
    }
    appendLog({ message: 'WebSocket not connected', taskId: activeTaskIdRef.current, type: 'error', status: 'failed' })
    return false
  }, [appendLog])
=======
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
      appendLog({ message: 'WebSocket not connected', type: 'error', status: 'failed', taskId: activeTaskIdRef.current })
      return false
    },
    [appendLog],
  )
>>>>>>> theirs

  const resetClientState = useCallback(() => {
    setLogs([])
    setLatestFrame('')
    setCurrentUrl('about:blank')
    setIsWorking(false)
<<<<<<< ours
    setWorkflowSteps([])
    activeTaskIdRef.current = 'idle'
  }, [])

  return { connectionStatus, isWorking, latestFrame, logs, workflowSteps, currentUrl, send, resetClientState, setLogs, setWorkflowSteps }
}

=======
    setActiveTaskId('idle')
    activeTaskIdRef.current = 'idle'
  }, [])

  return {
    connectionStatus,
    isWorking,
    latestFrame,
    logs,
    currentUrl,
    send,
    resetClientState,
  }
}
>>>>>>> theirs
