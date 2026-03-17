import { useCallback, useEffect, useRef, useState } from 'react'

const TARGET_SAMPLE_RATE = 16000
const BUFFER_SIZE = 4096

type UseMicrophoneOptions = {
  onChunk: (payload: string) => void
}

function downsampleBuffer(buffer: Float32Array, inputSampleRate: number, outputSampleRate: number): Float32Array {
  if (outputSampleRate === inputSampleRate) return buffer
  const sampleRateRatio = inputSampleRate / outputSampleRate
  const newLength = Math.round(buffer.length / sampleRateRatio)
  const result = new Float32Array(newLength)
  let offsetResult = 0
  let offsetBuffer = 0
  while (offsetResult < result.length) {
    const nextOffsetBuffer = Math.round((offsetResult + 1) * sampleRateRatio)
    let accum = 0
    let count = 0
    for (let i = offsetBuffer; i < nextOffsetBuffer && i < buffer.length; i += 1) {
      accum += buffer[i]
      count += 1
    }
    result[offsetResult] = accum / Math.max(1, count)
    offsetResult += 1
    offsetBuffer = nextOffsetBuffer
  }
  return result
}

function floatTo16BitPCM(input: Float32Array): Int16Array {
  const output = new Int16Array(input.length)
  for (let i = 0; i < input.length; i += 1) {
    const s = Math.max(-1, Math.min(1, input[i]))
    output[i] = s < 0 ? s * 0x8000 : s * 0x7fff
  }
  return output
}

function toBase64(int16: Int16Array): string {
  const bytes = new Uint8Array(int16.buffer)
  let binary = ''
  const chunkSize = 0x8000
  for (let i = 0; i < bytes.length; i += chunkSize) {
    const chunk = bytes.subarray(i, i + chunkSize)
    binary += String.fromCharCode(...chunk)
  }
  return btoa(binary)
}

export function useMicrophone({ onChunk }: UseMicrophoneOptions) {
  const [isActive, setIsActive] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const audioContextRef = useRef<AudioContext | null>(null)
  const processorRef = useRef<ScriptProcessorNode | null>(null)
  const sourceRef = useRef<MediaStreamAudioSourceNode | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const activeRef = useRef(false)

  const stop = useCallback(async () => {
    activeRef.current = false
    setIsActive(false)
    if (processorRef.current) {
      processorRef.current.disconnect()
      processorRef.current.onaudioprocess = null
      processorRef.current = null
    }
    if (sourceRef.current) {
      sourceRef.current.disconnect()
      sourceRef.current = null
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop())
      streamRef.current = null
    }
    if (audioContextRef.current) {
      await audioContextRef.current.close()
      audioContextRef.current = null
    }
  }, [])

  const start = useCallback(async () => {
    if (activeRef.current) return
    activeRef.current = true
    if (!navigator.mediaDevices?.getUserMedia) {
      setError('Microphone access is not supported in this browser.')
      activeRef.current = false
      return
    }
    if (typeof AudioContext === 'undefined') {
      setError('Audio context is not supported in this browser.')
      activeRef.current = false
      return
    }
    setError(null)
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, channelCount: 1 },
      })
      const audioContext = new AudioContext()
      const source = audioContext.createMediaStreamSource(stream)
      const processor = audioContext.createScriptProcessor(BUFFER_SIZE, 1, 1)
      const sink = audioContext.createGain()
      sink.gain.value = 0

      processor.onaudioprocess = (event) => {
        if (!activeRef.current) return
        const input = event.inputBuffer.getChannelData(0)
        const downsampled = downsampleBuffer(input, audioContext.sampleRate, TARGET_SAMPLE_RATE)
        const pcm = floatTo16BitPCM(downsampled)
        const payload = toBase64(pcm)
        onChunk(payload)
      }

      source.connect(processor)
      processor.connect(sink)
      sink.connect(audioContext.destination)
      await audioContext.resume()

      streamRef.current = stream
      audioContextRef.current = audioContext
      sourceRef.current = source
      processorRef.current = processor
      setIsActive(true)
    } catch (err) {
      activeRef.current = false
      await stop()
      setError(err instanceof Error ? err.message : 'Microphone access failed.')
    }
  }, [onChunk, stop])

  const toggle = useCallback(async () => {
    if (activeRef.current) {
      await stop()
    } else {
      await start()
    }
  }, [start, stop])

  useEffect(() => {
    return () => {
      void stop()
    }
  }, [stop])

  const isSupported = typeof navigator !== 'undefined' && Boolean(navigator.mediaDevices?.getUserMedia)

  return { isActive, error, isSupported, start, stop, toggle }
}
