import asyncio, subprocess, sys
REPO = '/work/repos/aegis-ui-agent'

def run_git(args: list[str], cwd: str) -> dict:
    """Run a git command and return the result."""
    result = subprocess.run(
        ['git'] + args,
        cwd=cwd,
        capture_output=True,
        text=True
    )
    return {'returncode': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr}

async def main():
    # Check git status
    r = run_git(['status', '--short'], REPO)
    if r.get('stdout', '').strip():
        # Stage all changes
        run_git(['add', '-A'], REPO)
        # Commit
        run_git(['commit', '-m', 'chore: remove temp scripts'], REPO)
        # Push
        run_git(['push', 'origin', 'main'], REPO)
        print("Cleaned up")
    else:
        print("Nothing to clean")

asyncio.run(main())
