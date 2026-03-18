import asyncio, sys
sys.path.insert(0, '/work')
from sdk.internal.client import get_client

REPO = '/work/repos/aegis-ui-agent'
COMMIT_MSG = """feat: provider + model picker on main screen, latest models for all providers

Model updates (researched from official docs, March 2026):
- OpenAI: GPT-5.2, GPT-5.2 Pro, GPT-5, GPT-5 Mini/Nano, GPT-4.1, o4-mini, o3
- Anthropic: Claude Opus 4.6, Sonnet 4.6, Haiku 4.5 (1M context)
- Google: Gemini 3.1 Pro Preview, 3.1 Flash-Lite, 3 Flash, 2.5 Pro/Flash
- Mistral: Large 3, Medium 3.1, Small 4, Codestral, Pixtral Large, Devstral Small
- Groq: Llama 4 Scout 17B, Llama 3.3 70B, GPT-OSS 120B/20B, Kimi K2

UI changes:
- InputBar: Provider picker dropdown + Model picker (replaces flat Google-only select)
- Selecting a provider loads that provider's models in the model dropdown
- AgentTab in Settings uses same new ModelInfo structure
- Added 'provider' field to AppSettings for persistence
- wsConfig now sends provider to backend
- models.ts: Structured ModelInfo type with label, description, vision flag
- All backend provider adapters updated with latest model lists"""

async def main():
    c = get_client()
    print("Staging...")
    await c.call('coworker_git', args=['add', '-A'], working_dir=REPO)
    r = await c.call('coworker_git', args=['status', '--short'], working_dir=REPO)
    print(r.get('stdout', ''))
    print("Committing...")
    r = await c.call('coworker_git', args=['commit', '-m', COMMIT_MSG], working_dir=REPO)
    print(f"  commit: {r.get('success')} — {r.get('stdout','')[:150]}")
    print("Pushing...")
    r = await c.call('coworker_git', args=['push', 'origin', 'main'], working_dir=REPO)
    print(f"  push: {r.get('success')} — {r.get('stderr','')[:150]}")

asyncio.run(main())
