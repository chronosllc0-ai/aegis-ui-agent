import { CHRONOS_LOGO_URL } from '../lib/models'

type Props = {
  onGoHome: () => void
  onGoAuth: () => void
}

interface Section {
  id: string
  title: string
  content: React.ReactNode
}

const EFFECTIVE_DATE = 'March 23, 2026'
const COMPANY = 'Chronos Intelligence Systems'
const PRODUCT = 'Aegis'
const SITE = 'mohex.org'
const CONTACT_EMAIL = 'privacy@mohex.org'

export function PrivacyPage({ onGoHome, onGoAuth }: Props) {
  const sections: Section[] = [
    {
      id: 'overview',
      title: '1. Overview',
      content: (
        <>
          <p>
            {COMPANY} ("<strong>Chronos</strong>", "<strong>we</strong>", "<strong>us</strong>", or "<strong>our</strong>")
            operates {PRODUCT} at <code>{SITE}</code> — an AI-powered browser automation agent platform.
            This Privacy Policy explains what personal data we collect, why we collect it, how we store and protect it,
            with whom we share it, and what rights you have over it.
          </p>
          <p className='mt-3'>
            By creating an account or using {PRODUCT}, you agree to this policy. If you do not agree, please do not use the service.
          </p>
        </>
      ),
    },
    {
      id: 'data-collected',
      title: '2. Data We Collect',
      content: (
        <>
          <p className='font-medium text-zinc-200'>2.1 Account Information</p>
          <p className='mt-1'>
            When you register or sign in, we collect your <strong>email address</strong>, <strong>display name</strong>,
            and <strong>profile picture URL</strong> (if you sign in via Google or GitHub OAuth). For password-based accounts
            we store a one-way <strong>bcrypt hash</strong> of your password — we never store your plaintext password.
          </p>

          <p className='mt-4 font-medium text-zinc-200'>2.2 OAuth Connection Tokens</p>
          <p className='mt-1'>
            When you connect external services (Google, GitHub, Slack, Notion, Linear) via the Connections tab,
            we receive and store OAuth 2.0 access and refresh tokens issued by those providers. These tokens are
            <strong> encrypted at rest</strong> using Fernet symmetric encryption (AES-128-CBC + HMAC-SHA256) before
            being written to the database. We use these tokens solely to perform actions you explicitly request.
          </p>

          <p className='mt-4 font-medium text-zinc-200'>2.3 API Keys (BYOK)</p>
          <p className='mt-1'>
            If you enter your own API keys for AI providers (OpenAI, Anthropic, xAI, OpenRouter), each key is
            <strong> encrypted at rest</strong> using the same Fernet scheme and stored per-user. Keys are decrypted
            in-memory only when making a request to the respective provider and are never logged or transmitted
            in plaintext. We store only a masked hint (last 4 characters) for display purposes.
          </p>

          <p className='mt-4 font-medium text-zinc-200'>2.4 Conversation &amp; Task History</p>
          <p className='mt-1'>
            We store the messages and instructions you send to {PRODUCT}, along with AI responses and structured task logs.
            This data is used to provide conversation continuity, display your task history, and improve the product.
          </p>

          <p className='mt-4 font-medium text-zinc-200'>2.5 Usage &amp; Credit Events</p>
          <p className='mt-1'>
            We record credit consumption events (model used, token counts, cost in credits) to power the Usage
            dashboard and enforce credit limits. These records are tied to your account.
          </p>

          <p className='mt-4 font-medium text-zinc-200'>2.6 Support Messages</p>
          <p className='mt-1'>
            If you submit a support request through the in-app support tab, we store the thread subject,
            message content, and any attachments you provide, associated with your account.
          </p>

          <p className='mt-4 font-medium text-zinc-200'>2.7 Technical Data</p>
          <p className='mt-1'>
            We log standard server-side metadata including IP address, browser user-agent, HTTP request paths,
            and timestamps for security monitoring, error tracking, and abuse prevention. We do not use third-party
            analytics scripts (e.g., Google Analytics) on the application.
          </p>

          <p className='mt-4 font-medium text-zinc-200'>2.8 Session Cookies</p>
          <p className='mt-1'>
            We set a single HTTP-only session cookie to maintain your authenticated session. This cookie is not used
            for advertising or cross-site tracking. It expires when you log out or after a configurable inactivity period.
          </p>
        </>
      ),
    },
    {
      id: 'how-we-use',
      title: '3. How We Use Your Data',
      content: (
        <ul className='space-y-2'>
          {[
            'To authenticate you and maintain your session.',
            'To execute browser automation tasks and AI agent workflows you initiate.',
            'To connect to external services on your behalf when you use OAuth connectors.',
            'To route AI requests to providers using your BYOK keys or platform default keys.',
            'To display your conversation history, usage statistics, and credit balance.',
            'To respond to support requests you submit.',
            'To detect and prevent abuse, security incidents, and policy violations.',
            'To improve the reliability and features of the platform.',
          ].map((item) => (
            <li key={item} className='flex gap-2'>
              <span className='mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-cyan-400' />
              <span>{item}</span>
            </li>
          ))}
        </ul>
      ),
    },
    {
      id: 'storage-security',
      title: '4. Data Storage & Security',
      content: (
        <>
          <p>
            All user data is stored in a <strong>PostgreSQL database</strong> hosted on{' '}
            <a href='https://railway.app' className='text-cyan-400 underline underline-offset-2 hover:text-cyan-300' target='_blank' rel='noopener noreferrer'>Railway</a>{' '}
            infrastructure, operating in a secured private network. Sensitive values (OAuth tokens, API keys) are
            encrypted before being written to the database using Fernet encryption; the encryption key is stored
            separately as an environment variable and is never committed to source code.
          </p>
          <p className='mt-3'>
            The frontend is served via{' '}
            <a href='https://netlify.com' className='text-cyan-400 underline underline-offset-2 hover:text-cyan-300' target='_blank' rel='noopener noreferrer'>Netlify</a>{' '}
            CDN over HTTPS (TLS 1.2+). All communication between the browser and the backend is encrypted in transit.
          </p>
          <p className='mt-3'>
            We apply the principle of least privilege: only the specific service processes that need to decrypt a
            credential can do so, and only at the moment of use.
          </p>
          <p className='mt-3'>
            Despite these measures, no system is 100% secure. If you discover a security vulnerability, please
            report it responsibly to <a href={`mailto:${CONTACT_EMAIL}`} className='text-cyan-400 underline underline-offset-2 hover:text-cyan-300'>{CONTACT_EMAIL}</a>.
          </p>
        </>
      ),
    },
    {
      id: 'third-parties',
      title: '5. Third-Party Services',
      content: (
        <>
          <p className='mb-3'>
            We do not sell your personal data. We share data only with the following categories of third parties,
            strictly as needed to operate the service:
          </p>
          <div className='overflow-x-auto rounded-lg border border-[#2a2a2a]'>
            <table className='w-full text-sm'>
              <thead>
                <tr className='border-b border-[#2a2a2a] bg-[#111]'>
                  <th className='px-4 py-3 text-left text-[11px] uppercase tracking-widest text-zinc-500'>Service</th>
                  <th className='px-4 py-3 text-left text-[11px] uppercase tracking-widest text-zinc-500'>Purpose</th>
                  <th className='px-4 py-3 text-left text-[11px] uppercase tracking-widest text-zinc-500'>Data shared</th>
                </tr>
              </thead>
              <tbody className='divide-y divide-[#2a2a2a]'>
                {[
                  ['Railway', 'Backend hosting & database', 'All stored data resides on Railway infrastructure'],
                  ['Netlify', 'Frontend CDN hosting', 'Static assets only — no user data'],
                  ['OpenAI', 'AI model inference (if BYOK set)', 'Your instructions & conversation context per request'],
                  ['Anthropic', 'AI model inference (if BYOK set)', 'Your instructions & conversation context per request'],
                  ['xAI', 'AI model inference (if BYOK set)', 'Your instructions & conversation context per request'],
                  ['OpenRouter', 'AI model routing (if BYOK set)', 'Your instructions & conversation context per request'],
                  ['Google', 'OAuth sign-in & connector', 'Auth code exchange; then your Google data only as you direct'],
                  ['GitHub', 'OAuth sign-in & connector', 'Auth code exchange; then your GitHub data only as you direct'],
                  ['Slack', 'OAuth connector', 'Auth code exchange; then your Slack data only as you direct'],
                  ['Notion', 'OAuth connector', 'Auth code exchange; then your Notion data only as you direct'],
                  ['Linear', 'OAuth connector', 'Auth code exchange; then your Linear data only as you direct'],
                ].map(([service, purpose, data]) => (
                  <tr key={service} className='hover:bg-white/2'>
                    <td className='px-4 py-3 font-medium text-zinc-200'>{service}</td>
                    <td className='px-4 py-3 text-zinc-400'>{purpose}</td>
                    <td className='px-4 py-3 text-zinc-500'>{data}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className='mt-3 text-xs text-zinc-500'>
            AI providers receive only the content of individual requests — not your email, name, API keys,
            or OAuth tokens. Each provider processes data under their own privacy policies.
          </p>
        </>
      ),
    },
    {
      id: 'retention',
      title: '6. Data Retention',
      content: (
        <>
          <p>
            We retain your data for as long as your account is active. Specific retention rules:
          </p>
          <ul className='mt-3 space-y-2'>
            {[
              ['Account data', 'Retained until you delete your account.'],
              ['Conversation history', 'Retained until you delete your account or clear history.'],
              ['OAuth tokens', 'Deleted when you disconnect a connector or delete your account.'],
              ['API keys', 'Deleted when you remove a key or delete your account.'],
              ['Usage / credit records', 'Retained for 12 months for billing and dispute resolution.'],
              ['Server logs', 'Retained for up to 30 days for security purposes.'],
              ['Support messages', 'Retained until your account is deleted or you request removal.'],
            ].map(([item, desc]) => (
              <li key={item as string} className='flex gap-2'>
                <span className='mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-cyan-400' />
                <span><strong className='text-zinc-200'>{item}:</strong> {desc}</span>
              </li>
            ))}
          </ul>
        </>
      ),
    },
    {
      id: 'your-rights',
      title: '7. Your Rights',
      content: (
        <>
          <p>Depending on your jurisdiction, you may have the following rights regarding your personal data:</p>
          <ul className='mt-3 space-y-2'>
            {[
              ['Access', 'Request a copy of the personal data we hold about you.'],
              ['Correction', 'Request correction of inaccurate data.'],
              ['Deletion', 'Request deletion of your account and associated data.'],
              ['Portability', 'Request your data in a machine-readable format.'],
              ['Objection / restriction', 'Object to or restrict certain processing activities.'],
              ['Withdraw consent', 'Revoke OAuth connections at any time via Settings → Connections.'],
            ].map(([right, desc]) => (
              <li key={right as string} className='flex gap-2'>
                <span className='mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-cyan-400' />
                <span><strong className='text-zinc-200'>{right}:</strong> {desc}</span>
              </li>
            ))}
          </ul>
          <p className='mt-3'>
            To exercise any of these rights, contact us at{' '}
            <a href={`mailto:${CONTACT_EMAIL}`} className='text-cyan-400 underline underline-offset-2 hover:text-cyan-300'>{CONTACT_EMAIL}</a>.
            We will respond within 30 days. Identity verification may be required before we process requests.
          </p>
        </>
      ),
    },
    {
      id: 'childrens-privacy',
      title: "8. Children's Privacy",
      content: (
        <p>
          {PRODUCT} is not directed to individuals under the age of 16. We do not knowingly collect personal data
          from children. If we become aware that a child under 16 has provided personal data, we will delete it promptly.
          If you believe we have inadvertently collected such data, contact us at{' '}
          <a href={`mailto:${CONTACT_EMAIL}`} className='text-cyan-400 underline underline-offset-2 hover:text-cyan-300'>{CONTACT_EMAIL}</a>.
        </p>
      ),
    },
    {
      id: 'international',
      title: '9. International Data Transfers',
      content: (
        <p>
          {COMPANY} is a global service. Your data may be processed in countries outside your own, including the
          United States where our infrastructure providers (Railway, Netlify) operate data centers. By using {PRODUCT},
          you consent to such transfers. We take reasonable steps to ensure data is protected to at least the standard
          required by applicable law.
        </p>
      ),
    },
    {
      id: 'changes',
      title: '10. Changes to This Policy',
      content: (
        <p>
          We may update this Privacy Policy from time to time. When we do, we will update the effective date at the
          top of this page and, for material changes, notify you via email or in-app notice. Continued use of{' '}
          {PRODUCT} after changes take effect constitutes your acceptance of the updated policy.
        </p>
      ),
    },
    {
      id: 'contact',
      title: '11. Contact Us',
      content: (
        <>
          <p>For privacy-related questions, requests, or concerns:</p>
          <div className='mt-3 rounded-lg border border-[#2a2a2a] bg-[#111] p-4 text-sm'>
            <p className='font-semibold text-zinc-200'>{COMPANY}</p>
            <p className='mt-1 text-zinc-400'>
              Email:{' '}
              <a href={`mailto:${CONTACT_EMAIL}`} className='text-cyan-400 underline underline-offset-2 hover:text-cyan-300'>
                {CONTACT_EMAIL}
              </a>
            </p>
            <p className='mt-1 text-zinc-400'>Website: <a href={`https://${SITE}`} className='text-cyan-400 underline underline-offset-2 hover:text-cyan-300'>{SITE}</a></p>
          </div>
        </>
      ),
    },
  ]

  return (
    <div className='min-h-screen bg-[#090c13] text-zinc-300'>
      {/* Nav */}
      <nav className='sticky top-0 z-20 border-b border-white/8 bg-[#090c13]/95 backdrop-blur'>
        <div className='mx-auto flex max-w-5xl items-center justify-between px-6 py-4'>
          <button type='button' onClick={onGoHome} className='flex items-center gap-3'>
            <img src={CHRONOS_LOGO_URL} alt='Chronos AI' className='h-7 w-7 rounded-full' />
            <span className='font-semibold text-white'>{PRODUCT}</span>
          </button>
          <button
            type='button'
            onClick={onGoAuth}
            className='rounded-full bg-cyan-500 px-4 py-1.5 text-sm font-medium text-slate-950 transition hover:bg-cyan-400'
          >
            Sign in
          </button>
        </div>
      </nav>

      {/* Hero */}
      <header className='border-b border-white/8 bg-gradient-to-b from-[#0d1117] to-[#090c13] px-6 py-14 text-center'>
        <span className='inline-block rounded-full border border-cyan-400/20 bg-cyan-400/8 px-3 py-1 text-xs font-medium uppercase tracking-widest text-cyan-400'>
          Legal
        </span>
        <h1 className='mt-4 text-4xl font-bold tracking-tight text-white'>Privacy Policy</h1>
        <p className='mt-3 text-sm text-zinc-500'>
          Effective date: <span className='text-zinc-400'>{EFFECTIVE_DATE}</span>
        </p>
      </header>

      <div className='mx-auto max-w-5xl px-6 py-12 lg:flex lg:gap-10'>
        {/* Sticky Table of Contents */}
        <aside className='mb-8 shrink-0 lg:mb-0 lg:w-56 xl:w-64'>
          <div className='sticky top-20 rounded-xl border border-[#2a2a2a] bg-[#111] p-4'>
            <p className='mb-3 text-[10px] uppercase tracking-[0.2em] text-zinc-500'>Contents</p>
            <nav className='space-y-1'>
              {sections.map((s) => (
                <a
                  key={s.id}
                  href={`#${s.id}`}
                  className='block rounded-md px-2 py-1.5 text-xs text-zinc-400 transition hover:bg-zinc-800 hover:text-white'
                >
                  {s.title}
                </a>
              ))}
            </nav>
          </div>
        </aside>

        {/* Policy content */}
        <main className='min-w-0 flex-1'>
          <div className='mb-8 rounded-xl border border-yellow-500/20 bg-yellow-500/8 px-5 py-4 text-sm text-yellow-200/80'>
            <strong className='font-semibold text-yellow-300'>Summary:</strong> We collect only what is necessary to
            operate {PRODUCT}. We encrypt sensitive data (tokens, keys) at rest. We do not sell your data. You can
            delete your account and all associated data at any time.
          </div>

          <div className='space-y-12'>
            {sections.map((s) => (
              <section key={s.id} id={s.id} className='scroll-mt-24'>
                <h2 className='mb-4 text-xl font-semibold text-white'>{s.title}</h2>
                <div className='text-sm leading-7 text-zinc-400'>{s.content}</div>
              </section>
            ))}
          </div>

          <div className='mt-12 border-t border-[#2a2a2a] pt-8 text-xs text-zinc-600'>
            <p>© {new Date().getFullYear()} {COMPANY}. All rights reserved.</p>
            <p className='mt-1'>
              Questions?{' '}
              <a href={`mailto:${CONTACT_EMAIL}`} className='text-zinc-500 underline underline-offset-2 hover:text-zinc-300'>
                {CONTACT_EMAIL}
              </a>
            </p>
          </div>
        </main>
      </div>
    </div>
  )
}
