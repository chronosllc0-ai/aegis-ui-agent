import { getRelatedDocs, type DocsBlock, type DocsPage } from '../docs'
import { SharedIcons } from './SharedIcons'

type DocsArticleProps = {
  page: DocsPage
  onNavigate: (slug: string) => void
}

function toneClasses(tone: 'info' | 'success' | 'warning'): string {
  if (tone === 'success') return 'border-emerald-400/30 bg-emerald-500/10 text-emerald-100'
  if (tone === 'warning') return 'border-amber-400/30 bg-amber-500/10 text-amber-100'
  return 'border-blue-400/30 bg-blue-500/10 text-blue-100'
}

function renderBlock(block: DocsBlock, index: number, onNavigate: (slug: string) => void) {
  switch (block.type) {
    case 'heading':
      return <h2 key={index} className='mt-10 text-xl font-semibold text-white'>{block.text}</h2>
    case 'paragraph':
      return <p key={index} className='text-sm leading-7 text-zinc-300'>{block.text}</p>
    case 'list':
      return (
        <ul key={index} className='grid gap-3 text-sm text-zinc-200'>
          {block.items.map((item) => (
            <li key={item} className='flex gap-3 rounded-2xl border border-white/6 bg-white/3 px-4 py-3'>
              {SharedIcons.check({ className: 'mt-0.5 h-4 w-4 shrink-0 text-cyan-300' })}
              <span>{item}</span>
            </li>
          ))}
        </ul>
      )
    case 'steps':
      return (
        <div key={index} className='grid gap-4'>
          {block.items.map((item, stepIndex) => (
            <article key={item.title} className='rounded-3xl border border-white/8 bg-white/4 p-5'>
              <div className='flex items-center gap-3'>
                <span className='inline-flex h-8 w-8 items-center justify-center rounded-full border border-cyan-400/30 bg-cyan-400/10 text-xs font-semibold text-cyan-200'>
                  {stepIndex + 1}
                </span>
                <h3 className='text-base font-semibold text-white'>{item.title}</h3>
              </div>
              <p className='mt-3 text-sm leading-7 text-zinc-300'>{item.body}</p>
            </article>
          ))}
        </div>
      )
    case 'callout':
      return (
        <div key={index} className={`rounded-3xl border p-5 ${toneClasses(block.tone)}`}>
          <p className='text-xs uppercase tracking-[0.2em]'>{block.title}</p>
          <p className='mt-3 text-sm leading-7'>{block.body}</p>
        </div>
      )
    case 'code':
      return (
        <div key={index} className='overflow-hidden rounded-3xl border border-white/8 bg-[#08111f]'>
          <div className='border-b border-white/8 px-4 py-3 text-[11px] uppercase tracking-[0.2em] text-cyan-200'>{block.language}</div>
          <pre className='m-0 overflow-x-auto px-4 py-4 text-sm leading-6 text-zinc-100'>
            <code>{block.code}</code>
          </pre>
        </div>
      )
    case 'table':
      return (
        <div key={index} className='overflow-hidden rounded-3xl border border-white/8 bg-white/3'>
          <div className='overflow-x-auto'>
            <table className='min-w-full border-collapse text-left text-sm'>
              <thead className='bg-white/6 text-zinc-200'>
                <tr>
                  {block.columns.map((column) => (
                    <th key={column} className='px-4 py-3 font-medium'>{column}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {block.rows.map((row, rowIndex) => (
                  <tr key={`${row[0]}-${rowIndex}`} className='border-t border-white/6 text-zinc-300'>
                    {row.map((cell) => (
                      <td key={cell} className='px-4 py-3 align-top'>{cell}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )
    case 'faq':
      return (
        <div key={index} className='grid gap-4'>
          {block.items.map((item) => (
            <article key={item.question} className='rounded-3xl border border-white/8 bg-white/4 p-5'>
              <h3 className='text-base font-semibold text-white'>{item.question}</h3>
              <p className='mt-3 text-sm leading-7 text-zinc-300'>{item.answer}</p>
            </article>
          ))}
        </div>
      )
    case 'timeline':
      return (
        <div key={index} className='grid gap-4'>
          {block.items.map((item) => (
            <article key={`${item.date}-${item.title}`} className='rounded-3xl border border-white/8 bg-white/4 p-5'>
              <p className='text-[11px] uppercase tracking-[0.2em] text-cyan-200'>{item.date}</p>
              <h3 className='mt-2 text-base font-semibold text-white'>{item.title}</h3>
              <p className='mt-3 text-sm leading-7 text-zinc-300'>{item.description}</p>
            </article>
          ))}
        </div>
      )
    case 'linkCards':
      return (
        <div key={index} className='grid gap-4 md:grid-cols-3'>
          {block.items.map((item) => (
            <button
              key={item.slug}
              type='button'
              onClick={() => onNavigate(item.slug)}
              className='rounded-3xl border border-white/8 bg-white/4 p-5 text-left transition hover:border-cyan-400/30 hover:bg-cyan-400/6'
            >
              <p className='text-sm font-semibold text-white'>{item.title}</p>
              <p className='mt-3 text-sm leading-7 text-zinc-300'>{item.description}</p>
            </button>
          ))}
        </div>
      )
  }
}

export function DocsArticle({ page, onNavigate }: DocsArticleProps) {
  const related = getRelatedDocs(page)

  return (
    <article className='grid gap-6'>
      <header className='rounded-[32px] border border-white/8 bg-[radial-gradient(circle_at_top,rgba(34,211,238,0.16),transparent_35%),linear-gradient(180deg,#101625_0%,#0a0d14_100%)] p-8 shadow-[0_24px_80px_rgba(0,0,0,0.35)]'>
        <p className='text-[11px] uppercase tracking-[0.24em] text-cyan-200'>{page.section}</p>
        <h1 className='mt-4 text-4xl font-semibold text-white'>{page.title}</h1>
        <p className='mt-4 max-w-3xl text-base leading-8 text-zinc-300'>{page.summary}</p>
        <div className='mt-6 flex flex-wrap gap-3 text-xs text-zinc-400'>
          <span className='rounded-full border border-white/10 px-3 py-1'>Audience: {page.audience}</span>
          <span className='rounded-full border border-white/10 px-3 py-1'>Updated: {page.updatedAt}</span>
        </div>
      </header>

      <div className='grid gap-5 rounded-[32px] border border-white/8 bg-[#0c1018] p-8'>
        {page.blocks.map((block, index) => renderBlock(block, index, onNavigate))}
      </div>

      {related.length > 0 && (
        <section className='grid gap-4'>
          <div className='flex items-center gap-3'>
            {SharedIcons.workflows({ className: 'h-4 w-4 text-cyan-200' })}
            <h2 className='text-lg font-semibold text-white'>Related docs</h2>
          </div>
          <div className='grid gap-4 md:grid-cols-3'>
            {related.map((item) => (
              <button
                key={item.slug}
                type='button'
                onClick={() => onNavigate(item.slug)}
                className='rounded-3xl border border-white/8 bg-white/4 p-5 text-left transition hover:border-cyan-400/30 hover:bg-cyan-400/6'
              >
                <p className='text-sm font-semibold text-white'>{item.title}</p>
                <p className='mt-3 text-sm leading-7 text-zinc-300'>{item.summary}</p>
              </button>
            ))}
          </div>
        </section>
      )}
    </article>
  )
}
