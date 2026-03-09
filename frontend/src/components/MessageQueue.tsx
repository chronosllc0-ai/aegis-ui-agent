type MessageQueueProps = {
  queuedMessages: string[]
  isOpen: boolean
  onToggle: () => void
  onDelete: (index: number) => void
}

export function MessageQueue({ queuedMessages, isOpen, onToggle, onDelete }: MessageQueueProps) {
  return (
    <div className='rounded-lg border border-[#2a2a2a] bg-[#111] p-2'>
      <button type='button' onClick={onToggle} className='flex w-full items-center justify-between text-xs text-zinc-300'>
        <span>Queued Instructions</span>
        <span className='rounded-full bg-blue-500 px-2 py-0.5 text-white'>{queuedMessages.length}</span>
      </button>
      {isOpen && (
        <ul className='mt-2 space-y-1'>
          {queuedMessages.map((message, index) => (
            <li key={`${message}-${index}`} className='flex items-center justify-between rounded border border-[#2a2a2a] p-2 text-xs text-zinc-300'>
              <span className='mr-2'>{index + 1}. {message.length > 50 ? `${message.slice(0, 50)}...` : message}</span>
              <button type='button' onClick={() => onDelete(index)} className='text-red-300 hover:text-red-200'>✕</button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
