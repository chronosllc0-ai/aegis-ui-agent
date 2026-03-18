import asyncio, sys
sys.path.insert(0, '/work')
from sdk.internal.client import get_client
REPO = '/work/repos/aegis-ui-agent'
async def main():
    c = get_client()
    await c.call('coworker_git', args=['add', '-A'], working_dir=REPO)
    r = await c.call('coworker_git', args=['status', '--short'], working_dir=REPO)
    if r.get('stdout','').strip():
        await c.call('coworker_git', args=['commit', '-m', 'chore: remove temp scripts'], working_dir=REPO)
        await c.call('coworker_git', args=['push', 'origin', 'main'], working_dir=REPO)
        print("Cleaned up")
    else:
        print("Nothing to clean")
asyncio.run(main())
