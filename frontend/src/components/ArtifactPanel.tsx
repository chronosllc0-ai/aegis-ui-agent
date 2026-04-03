import { useState } from 'react'
import { useArtifacts } from '../hooks/useArtifacts'

export function ArtifactPanel() {
  const { artifacts, loading, load, getDownloadUrl } = useArtifacts()
  const [loaded, setLoaded] = useState(false)

  const handleLoad = async () => {
    await load()
    setLoaded(true)
  }

  return (
    <section className='space-y-2 rounded-xl border border-[#2a2a2a] bg-[#1a1a1a] p-3'>
      <div className='flex items-center justify-between'>
        <h3 className='text-sm font-semibold text-zinc-100'>Artifacts</h3>
        <button type='button' onClick={() => void handleLoad()} className='rounded border border-[#2a2a2a] px-2 py-1 text-xs text-zinc-300 hover:bg-zinc-800'>
          {loaded ? 'Refresh' : 'Load'}
        </button>
      </div>
      {loading && <p className='text-xs text-zinc-400'>Loading artifacts…</p>}
      <div className='space-y-2'>
        {artifacts.map((artifact) => (
          <div key={artifact.id} className='rounded border border-[#2a2a2a] bg-[#111] p-2'>
            <p className='text-xs font-medium text-zinc-200'>{artifact.title}</p>
            <div className='mt-1 flex items-center justify-between text-[11px] text-zinc-500'>
              <span>{artifact.artifact_type}</span>
              <a href={getDownloadUrl(artifact.id)} className='text-blue-300 hover:text-blue-200'>Download</a>
            </div>
          </div>
        ))}
        {!loading && loaded && artifacts.length === 0 && <p className='text-xs text-zinc-500'>No artifacts yet.</p>}
      </div>
    </section>
  )
}
