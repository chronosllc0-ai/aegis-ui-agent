"""Add all changes, commit, and push to main via coworker_git SDK."""
import asyncio
import sys
sys.path.insert(0, '/work')

from sdk.internal.client import get_client

REPO = '/work/repos/aegis-ui-agent'
COMMIT_MSG = """feat: product pivot — multi-provider, BYOK, Railway, landing page redesign

Major changes:
- backend/providers/: Multi-model provider abstraction (OpenAI, Anthropic, Google, Mistral, Groq)
- backend/database.py: PostgreSQL/SQLAlchemy async (replaces Firestore)
- backend/key_management.py: AES-256 encrypted BYOK key storage
- auth.py: Rewritten for PostgreSQL (SQLAlchemy AsyncSession)
- config.py: New env vars for all providers, Railway, BYOK
- main.py: BYOK API endpoints, provider listing, DB lifecycle, v1.0.0
- requirements.txt: Added provider SDKs, SQLAlchemy, cryptography; removed GCP deps
- frontend/src/lib/models.ts: Full provider/model catalogue (30+ models)
- frontend/src/components/LandingPage.tsx: Complete redesign — hero, features, pricing, BYOK explainer
- frontend/src/components/settings/APIKeysTab.tsx: BYOK key management UI
- frontend/src/components/settings/AgentTab.tsx: Multi-provider model selector
- frontend/src/components/settings/SettingsPage.tsx: Added API Keys tab
- railway.json, railway.toml, Procfile: Railway deployment config
- Dockerfile: Multi-stage build with Railway PORT support
- docker-compose.yml: PostgreSQL + app services
- deploy-railway.sh: Railway deployment script
- .env.example: All new environment variables
- README.md: Updated for multi-provider SaaS product"""


async def main():
    c = get_client()

    # Stage all changes
    print("Staging all changes...")
    r = await c.call('coworker_git', args=['add', '-A'], working_dir=REPO)
    print(f"  add: {r}")

    # Check status
    r = await c.call('coworker_git', args=['status', '--short'], working_dir=REPO)
    print(f"  status:\n{r}")

    # Commit
    print("Committing...")
    r = await c.call('coworker_git', args=['commit', '-m', COMMIT_MSG], working_dir=REPO)
    print(f"  commit: {r}")

    # Push to main
    print("Pushing to main...")
    r = await c.call('coworker_git', args=['push', 'origin', 'main'], working_dir=REPO)
    print(f"  push: {r}")

    print("Done!")


asyncio.run(main())
