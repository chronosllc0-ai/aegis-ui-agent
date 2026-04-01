import { AEGIS_LOGO_URL } from '../lib/models'

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
const COMPANY = 'Chronos AI'
const PRODUCT = 'Aegis'
const SITE = 'mohex.org'
const CONTACT_EMAIL = 'legal@mohex.org'
const PRIVACY_EMAIL = 'privacy@mohex.org'

export function TermsPage({ onGoHome, onGoAuth }: Props) {
  const sections: Section[] = [
    {
      id: 'agreement',
      title: '1. Agreement to Terms',
      content: (
        <>
          <p>
            These Terms of Service ("Terms") constitute a legally binding agreement between you ("User", "you", or "your")
            and {COMPANY} ("Chronos", "we", "us", or "our"), governing your access to and use of {PRODUCT},
            available at <code>{SITE}</code> ("Service").
          </p>
          <p className='mt-3'>
            By creating an account, accessing, or using the Service in any way, you confirm that you have read,
            understood, and agree to be bound by these Terms and our Privacy Policy. If you do not agree, you must
            not access or use the Service.
          </p>
          <p className='mt-3'>
            If you are using the Service on behalf of an organisation, you represent that you have the authority to
            bind that organisation to these Terms, and all references to "you" include that organisation.
          </p>
        </>
      ),
    },
    {
      id: 'eligibility',
      title: '2. Eligibility',
      content: (
        <>
          <p>You may only use the Service if you:</p>
          <ul className='mt-2 list-inside list-disc space-y-1.5 text-zinc-300'>
            <li>Are at least 18 years of age, or have reached the age of majority in your jurisdiction;</li>
            <li>Have the legal capacity to enter into binding contracts;</li>
            <li>Are not barred from receiving services under applicable law;</li>
            <li>Are not located in a country subject to a U.S. government embargo or designated as a "terrorist supporting" country.</li>
          </ul>
          <p className='mt-3'>
            The Service is designed for professional and commercial use. It is not intended for consumer use
            by individuals acting in a purely personal capacity unrelated to trade, business, or profession.
          </p>
        </>
      ),
    },
    {
      id: 'account',
      title: '3. Accounts & Registration',
      content: (
        <>
          <p className='font-medium text-zinc-200'>3.1 Account Creation</p>
          <p className='mt-1'>
            You may register via email/password or OAuth (Google, GitHub). You are responsible for providing accurate,
            current, and complete information during registration and for keeping it up to date.
          </p>

          <p className='mt-4 font-medium text-zinc-200'>3.2 Account Security</p>
          <p className='mt-1'>
            You are solely responsible for maintaining the confidentiality of your login credentials and for all
            activities that occur under your account. You must immediately notify us at <code>{CONTACT_EMAIL}</code> of
            any suspected unauthorised use or security breach. We are not liable for any loss arising from
            unauthorised use of your account.
          </p>

          <p className='mt-4 font-medium text-zinc-200'>3.3 One Account per User</p>
          <p className='mt-1'>
            You may not create multiple accounts to circumvent credit limits, bans, or other restrictions.
            We reserve the right to merge, suspend, or terminate duplicate accounts.
          </p>

          <p className='mt-4 font-medium text-zinc-200'>3.4 Account Termination by You</p>
          <p className='mt-1'>
            You may delete your account at any time via the Profile settings tab. Deletion is permanent and
            irreversible. We will delete or anonymise your personal data in accordance with our Privacy Policy.
          </p>
        </>
      ),
    },
    {
      id: 'service-description',
      title: '4. Description of Service',
      content: (
        <>
          <p>
            {PRODUCT} is an AI-powered browser automation and agent orchestration platform. The Service allows
            you to:
          </p>
          <ul className='mt-2 list-inside list-disc space-y-1.5 text-zinc-300'>
            <li>Issue natural-language instructions to an AI agent that operates a virtual browser on your behalf;</li>
            <li>Connect third-party services (Google, GitHub, Slack, Notion, Linear, and others) via OAuth 2.0;</li>
            <li>Build and run reusable automated workflows;</li>
            <li>Use your own AI provider API keys (BYOK) to direct model inference.</li>
          </ul>
          <p className='mt-3'>
            The Service is provided as a managed cloud platform. We reserve the right to modify, add, or remove
            features at any time with or without notice, though we will make reasonable efforts to communicate
            material changes.
          </p>
        </>
      ),
    },
    {
      id: 'credits-billing',
      title: '5. Credits & Billing',
      content: (
        <>
          <p className='font-medium text-zinc-200'>5.1 Credit System</p>
          <p className='mt-1'>
            Access to certain Service features is metered via a credit system. Credits are consumed based on
            AI model usage, browser session duration, and other resource consumption as displayed in the Usage tab.
            Credit rates are subject to change with reasonable prior notice.
          </p>

          <p className='mt-4 font-medium text-zinc-200'>5.2 Bring Your Own Keys (BYOK)</p>
          <p className='mt-1'>
            If you supply your own API keys for AI providers, inference costs are billed directly by those
            providers under their terms. You remain responsible for all charges incurred via your API keys.
            We are not liable for provider-side billing or API rate limits.
          </p>

          <p className='mt-4 font-medium text-zinc-200'>5.3 No Refunds</p>
          <p className='mt-1'>
            All credit purchases are final and non-refundable except where required by applicable consumer
            protection law or at our sole discretion in exceptional circumstances. Credits have no cash value
            and cannot be transferred between accounts.
          </p>

          <p className='mt-4 font-medium text-zinc-200'>5.4 Taxes</p>
          <p className='mt-1'>
            You are responsible for all applicable taxes, duties, and levies arising from your use of the
            Service. Stated prices are exclusive of VAT/GST unless noted otherwise.
          </p>
        </>
      ),
    },
    {
      id: 'acceptable-use',
      title: '6. Acceptable Use',
      content: (
        <>
          <p>You agree not to use the Service to:</p>
          <ul className='mt-2 list-inside list-disc space-y-1.5 text-zinc-300'>
            <li>Violate any applicable law, regulation, or third-party rights;</li>
            <li>Scrape, harvest, or extract data from websites in violation of their terms of service;</li>
            <li>Generate, distribute, or facilitate spam, phishing, or fraudulent content;</li>
            <li>Conduct automated attacks on systems, networks, or infrastructure;</li>
            <li>Circumvent authentication, access controls, or security measures of any system;</li>
            <li>Create, train, or derive AI models using outputs of the Service without our written consent;</li>
            <li>Impersonate any person or entity;</li>
            <li>Engage in illegal surveillance, stalking, or harassment;</li>
            <li>Generate, distribute, or store child sexual abuse material or any content that exploits minors;</li>
            <li>Develop weapons, malware, or tools designed to cause harm;</li>
            <li>Interfere with or disrupt the integrity or performance of the Service;</li>
            <li>Attempt to gain unauthorised access to the Service or its underlying systems.</li>
          </ul>
          <p className='mt-3'>
            We reserve the right to investigate violations and take any action we deem appropriate, including
            immediate account suspension or termination, without prior notice or liability.
          </p>
        </>
      ),
    },
    {
      id: 'third-party',
      title: '7. Third-Party Integrations',
      content: (
        <>
          <p>
            The Service integrates with third-party platforms and APIs (including but not limited to Google,
            GitHub, Slack, Notion, Linear, OpenAI, Anthropic, xAI, and OpenRouter). Your use of these
            integrations is governed by the respective third-party terms of service and privacy policies.
          </p>
          <p className='mt-3'>
            We are not responsible for the availability, accuracy, or conduct of third-party services.
            Connecting an external service via OAuth grants {PRODUCT} the scopes you explicitly authorise;
            you can revoke access at any time via the Connections tab or directly through the third-party
            platform's settings.
          </p>
          <p className='mt-3'>
            We do not control, endorse, or assume responsibility for any third-party content or services
            accessed during automated browsing sessions initiated through the Service.
          </p>
        </>
      ),
    },
    {
      id: 'ip',
      title: '8. Intellectual Property',
      content: (
        <>
          <p className='font-medium text-zinc-200'>8.1 Our IP</p>
          <p className='mt-1'>
            The Service, including all software, interfaces, designs, logos, documentation, and AI agent
            infrastructure, is owned by {COMPANY} or its licensors and is protected by copyright, trademark,
            and other intellectual property laws. Nothing in these Terms grants you ownership of any Service
            component.
          </p>

          <p className='mt-4 font-medium text-zinc-200'>8.2 Licence to Use</p>
          <p className='mt-1'>
            Subject to your compliance with these Terms, we grant you a limited, non-exclusive, non-transferable,
            revocable licence to access and use the Service solely for your internal business or personal purposes.
          </p>

          <p className='mt-4 font-medium text-zinc-200'>8.3 Your Content</p>
          <p className='mt-1'>
            You retain all rights in content you upload, input, or generate ("User Content"). By using the Service,
            you grant us a limited, worldwide, royalty-free licence to process, store, and transmit User Content
            solely to provide the Service. We do not claim ownership of your content and will not use it to
            train AI models without your explicit consent.
          </p>

          <p className='mt-4 font-medium text-zinc-200'>8.4 Feedback</p>
          <p className='mt-1'>
            Any feedback, suggestions, or ideas you provide about the Service may be used by us freely and without
            obligation or compensation to you.
          </p>
        </>
      ),
    },
    {
      id: 'privacy',
      title: '9. Privacy',
      content: (
        <>
          <p>
            Our collection and use of your personal data is governed by our{' '}
            <a href='/privacy' className='text-cyan-400 underline hover:text-cyan-300'>Privacy Policy</a>,
            which is incorporated into these Terms by reference. By using the Service, you consent to the
            data practices described therein.
          </p>
          <p className='mt-3'>
            For privacy-related enquiries contact <code>{PRIVACY_EMAIL}</code>.
          </p>
        </>
      ),
    },
    {
      id: 'disclaimers',
      title: '10. Disclaimers',
      content: (
        <>
          <p>
            THE SERVICE IS PROVIDED ON AN <strong>"AS IS"</strong> AND <strong>"AS AVAILABLE"</strong> BASIS
            WITHOUT WARRANTIES OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO WARRANTIES OF
            MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE, NON-INFRINGEMENT, OR UNINTERRUPTED OR ERROR-FREE OPERATION.
          </p>
          <p className='mt-3'>
            We do not warrant that:
          </p>
          <ul className='mt-2 list-inside list-disc space-y-1.5 text-zinc-300'>
            <li>The Service will meet your specific requirements;</li>
            <li>AI-generated outputs will be accurate, complete, or suitable for your purposes;</li>
            <li>The Service will be available at any particular time or location;</li>
            <li>Browser automation sessions will complete successfully on all target websites;</li>
            <li>Any errors or defects will be corrected.</li>
          </ul>
          <p className='mt-3'>
            AI-generated content, automated actions, and agent outputs are experimental in nature. You are
            solely responsible for reviewing, validating, and acting on any output produced by the Service.
          </p>
        </>
      ),
    },
    {
      id: 'liability',
      title: '11. Limitation of Liability',
      content: (
        <>
          <p>
            TO THE MAXIMUM EXTENT PERMITTED BY APPLICABLE LAW, {COMPANY.toUpperCase()} AND ITS OFFICERS,
            DIRECTORS, EMPLOYEES, AGENTS, AND LICENSORS SHALL NOT BE LIABLE FOR ANY:
          </p>
          <ul className='mt-2 list-inside list-disc space-y-1.5 text-zinc-300'>
            <li>Indirect, incidental, special, consequential, or punitive damages;</li>
            <li>Loss of profits, revenue, data, goodwill, or business opportunities;</li>
            <li>Damages resulting from AI-generated outputs or automated actions taken on your behalf;</li>
            <li>Unauthorised access to or alteration of your data;</li>
            <li>Conduct or content of third-party services accessed via the platform.</li>
          </ul>
          <p className='mt-3'>
            IN NO EVENT SHALL OUR TOTAL CUMULATIVE LIABILITY TO YOU FOR ALL CLAIMS ARISING UNDER OR RELATED
            TO THESE TERMS EXCEED THE GREATER OF (A) THE AMOUNTS PAID BY YOU TO US IN THE 12 MONTHS
            PRECEDING THE CLAIM, OR (B) USD $100.
          </p>
          <p className='mt-3 text-sm text-zinc-500'>
            Some jurisdictions do not allow the exclusion or limitation of certain damages. In such jurisdictions,
            our liability is limited to the fullest extent permitted by law.
          </p>
        </>
      ),
    },
    {
      id: 'indemnification',
      title: '12. Indemnification',
      content: (
        <>
          <p>
            You agree to indemnify, defend, and hold harmless {COMPANY} and its officers, directors, employees,
            agents, and licensors from and against any claims, liabilities, damages, losses, and expenses
            (including reasonable legal fees) arising out of or in connection with:
          </p>
          <ul className='mt-2 list-inside list-disc space-y-1.5 text-zinc-300'>
            <li>Your use of the Service in violation of these Terms;</li>
            <li>Your User Content;</li>
            <li>Your automated actions performed via the Service;</li>
            <li>Your violation of any third-party right, including intellectual property rights;</li>
            <li>Your violation of any applicable law or regulation.</li>
          </ul>
        </>
      ),
    },
    {
      id: 'termination',
      title: '13. Suspension & Termination',
      content: (
        <>
          <p className='font-medium text-zinc-200'>13.1 By Us</p>
          <p className='mt-1'>
            We may suspend or terminate your access to the Service immediately, without prior notice or
            liability, for any reason including if you breach these Terms. Upon termination, your right to
            use the Service ceases immediately.
          </p>

          <p className='mt-4 font-medium text-zinc-200'>13.2 Effect of Termination</p>
          <p className='mt-1'>
            Sections 8 (Intellectual Property), 10 (Disclaimers), 11 (Limitation of Liability),
            12 (Indemnification), and 16 (Governing Law) survive termination. Credits or prepaid balances
            forfeited on termination for cause are non-refundable.
          </p>
        </>
      ),
    },
    {
      id: 'modifications',
      title: '14. Modifications to Terms',
      content: (
        <>
          <p>
            We reserve the right to update or modify these Terms at any time. If we make material changes,
            we will notify you by updating the "Effective Date" above and, where feasible, by posting a notice
            in the Service or sending an email to your registered address.
          </p>
          <p className='mt-3'>
            Your continued use of the Service after the effective date of any changes constitutes your acceptance
            of the revised Terms. If you do not agree to the revised Terms, you must stop using the Service.
          </p>
        </>
      ),
    },
    {
      id: 'service-changes',
      title: '15. Service Changes & Availability',
      content: (
        <>
          <p>
            We may modify, suspend, or discontinue the Service (or any part thereof) at any time with or
            without notice. We will endeavour to provide advance notice of significant changes where possible.
            We are not liable to you or any third party for any modification, suspension, or discontinuation
            of the Service.
          </p>
          <p className='mt-3'>
            We do not guarantee specific uptime levels unless expressly stated in a separate Service Level
            Agreement signed by both parties.
          </p>
        </>
      ),
    },
    {
      id: 'governing-law',
      title: '16. Governing Law & Disputes',
      content: (
        <>
          <p className='font-medium text-zinc-200'>16.1 Governing Law</p>
          <p className='mt-1'>
            These Terms are governed by and construed in accordance with the laws of the jurisdiction in which
            {COMPANY} is incorporated, without regard to conflict of law provisions.
          </p>

          <p className='mt-4 font-medium text-zinc-200'>16.2 Informal Resolution</p>
          <p className='mt-1'>
            Before initiating formal proceedings, you agree to first contact us at <code>{CONTACT_EMAIL}</code> and
            give us 30 days to attempt to resolve the dispute informally.
          </p>

          <p className='mt-4 font-medium text-zinc-200'>16.3 Dispute Resolution</p>
          <p className='mt-1'>
            Any dispute not resolved informally shall be subject to binding arbitration or, where arbitration
            is not enforceable under applicable law, the exclusive jurisdiction of courts in {COMPANY}'s
            place of incorporation. You waive any right to participate in class action litigation.
          </p>
        </>
      ),
    },
    {
      id: 'general',
      title: '17. General',
      content: (
        <>
          <p className='font-medium text-zinc-200'>17.1 Entire Agreement</p>
          <p className='mt-1'>
            These Terms and the Privacy Policy constitute the entire agreement between you and {COMPANY}
            regarding the Service and supersede all prior agreements and understandings.
          </p>

          <p className='mt-4 font-medium text-zinc-200'>17.2 Severability</p>
          <p className='mt-1'>
            If any provision of these Terms is found to be invalid or unenforceable, the remaining provisions
            continue in full force and effect.
          </p>

          <p className='mt-4 font-medium text-zinc-200'>17.3 Waiver</p>
          <p className='mt-1'>
            Our failure to enforce any right or provision of these Terms shall not constitute a waiver of
            that right or provision.
          </p>

          <p className='mt-4 font-medium text-zinc-200'>17.4 Assignment</p>
          <p className='mt-1'>
            You may not assign or transfer your rights under these Terms without our prior written consent.
            We may assign our rights to any successor entity in connection with a merger, acquisition, or
            sale of assets.
          </p>

          <p className='mt-4 font-medium text-zinc-200'>17.5 Force Majeure</p>
          <p className='mt-1'>
            We are not liable for any failure or delay in performance caused by circumstances beyond our
            reasonable control, including but not limited to natural disasters, government actions, internet
            outages, or third-party service failures.
          </p>
        </>
      ),
    },
    {
      id: 'contact',
      title: '18. Contact Us',
      content: (
        <>
          <p>For questions about these Terms, please contact us:</p>
          <div className='mt-3 rounded-lg border border-zinc-800 bg-zinc-900/50 p-4 text-sm'>
            <p className='font-medium text-zinc-200'>{COMPANY}</p>
            <p className='mt-1 text-zinc-400'>Legal enquiries: <code className='text-cyan-400'>{CONTACT_EMAIL}</code></p>
            <p className='mt-1 text-zinc-400'>Privacy enquiries: <code className='text-cyan-400'>{PRIVACY_EMAIL}</code></p>
            <p className='mt-1 text-zinc-400'>Website: <code className='text-cyan-400'>{SITE}</code></p>
          </div>
        </>
      ),
    },
  ]

  const toc = sections.map((s) => ({ id: s.id, title: s.title }))

  return (
    <div className='min-h-screen bg-[#090c13] text-zinc-300'>
      {/* Top nav */}
      <header className='sticky top-0 z-30 border-b border-white/8 bg-[#090c13]/90 backdrop-blur-md'>
        <div className='mx-auto flex max-w-7xl items-center justify-between px-6 py-4'>
          <button type='button' onClick={onGoHome} className='flex items-center gap-3'>
            <img src={AEGIS_LOGO_URL} alt='Aegis owl logo' className='h-8 w-8' />
            <span className='font-semibold text-white'>Aegis</span>
          </button>
          <div className='flex gap-3'>
            <button
              type='button'
              onClick={onGoHome}
              className='rounded-full border border-white/10 px-4 py-1.5 text-sm text-zinc-300 transition hover:border-cyan-400/30 hover:text-white'
            >
              Home
            </button>
            <button
              type='button'
              onClick={onGoAuth}
              className='rounded-full bg-cyan-500 px-4 py-1.5 text-sm font-medium text-slate-950 transition hover:bg-cyan-400'
            >
              Sign in
            </button>
          </div>
        </div>
      </header>

      <div className='mx-auto flex max-w-7xl gap-12 px-6 py-14'>
        {/* Sticky ToC sidebar */}
        <aside className='hidden w-64 shrink-0 lg:block'>
          <div className='sticky top-24'>
            <p className='mb-4 text-[11px] uppercase tracking-[0.2em] text-zinc-500'>Contents</p>
            <nav className='flex flex-col gap-1'>
              {toc.map((item) => (
                <a
                  key={item.id}
                  href={`#${item.id}`}
                  className='rounded-md px-3 py-1.5 text-sm text-zinc-400 transition hover:bg-white/5 hover:text-white'
                >
                  {item.title}
                </a>
              ))}
            </nav>
          </div>
        </aside>

        {/* Main content */}
        <main className='min-w-0 flex-1'>
          {/* Banner */}
          <div className='mb-10 rounded-xl border border-amber-500/20 bg-amber-500/8 p-5'>
            <p className='text-sm font-medium text-amber-300'>Terms of Service</p>
            <p className='mt-1 text-sm text-zinc-400'>
              Effective date: <strong className='text-zinc-200'>{EFFECTIVE_DATE}</strong>
            </p>
            <p className='mt-2 text-sm text-zinc-500'>
              By using {PRODUCT} you agree to these terms. Please read them carefully. If you have questions,
              contact <code className='text-cyan-400'>{CONTACT_EMAIL}</code>.
            </p>
          </div>

          <h1 className='mb-2 text-3xl font-bold text-white'>Terms of Service</h1>
          <p className='mb-10 text-zinc-500'>
            {COMPANY} · Last updated {EFFECTIVE_DATE}
          </p>

          <div className='space-y-14'>
            {sections.map((section) => (
              <section key={section.id} id={section.id} className='scroll-mt-28'>
                <h2 className='mb-4 text-xl font-semibold text-white'>{section.title}</h2>
                <div className='text-sm leading-7 text-zinc-400'>{section.content}</div>
              </section>
            ))}
          </div>

          {/* Bottom links */}
          <div className='mt-14 flex flex-wrap gap-6 border-t border-white/8 pt-10 text-sm text-zinc-500'>
            <button type='button' onClick={onGoHome} className='transition hover:text-white'>
              ← Back to home
            </button>
            <a href='/privacy' className='transition hover:text-white'>
              Privacy Policy
            </a>
            <button type='button' onClick={onGoAuth} className='transition hover:text-white'>
              Sign in
            </button>
          </div>
        </main>
      </div>
    </div>
  )
}
