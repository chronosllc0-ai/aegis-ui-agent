#!/usr/bin/env python3
"""Decode and parse a GitHub webhook payload."""

import urllib.parse
import json
from datetime import datetime

# The URL-encoded payload from the webhook
encoded_payload = (
    "payload=%7B%22action%22%3A%22synchronize%22%2C%22number%22%3A278%2C%22pull_request%22%3A%7B%22url%22%3A%22https%3A%2F%2Fapi.github.com%2Frepos%2Fchronosllc0-ai%2Faegis-ui-agent%2Fpulls%2F278%22%2C%22id%22%3A3545023030%2C%22node_id%22%3A%22PR_kwDORhlV2s7TTMI2%22%2C%22html_url%22%3A%22https%3A%2F%2Fgithub.com%2Fchronosllc0-ai%2Faegis-ui-agent%2Fpull%2F278%22%2C%22diff_url%22%3A%22https%3A%2F%2Fgithub.com%2Fchronosllc0-ai%2Faegis-ui-agent%2Fpull%2F278.diff%22%2C%22patch_url%22%3A%22https%3A%2F%2Fgithub.com%2Fchronosllc0-ai%2Faegis-ui-agent%2Fpull%2F278.patch%22%2C%22issue_url%22%3A%22https%3A%2F%2Fapi.github.com%2Frepos%2Fchronosllc0-ai%2Faegis-ui-agent%2Fissues%2F278%22%2C%22number%22%3A278%2C%22state%22%3A%22open%22%2C%22locked%22%3Afalse%2C%22title%22%3A%22Add+runtime+telemetry+and+channel+advanced-tool+feature+flags+with+regression+tests%22%2C%22user%22%3A%7B%22login%22%3A%22chronosllc0-ai%22%2C%22id%22%3A241236044%2C%22node_id%22%3A%22U_kgDODmD4TA%22%2C%22avatar_url%22%3A%22https%3A%2F%2Favatars.githubusercontent.com%2Fu%2F241236044%3Fv%3D4%22%2C%22gravatar_id%22%3A%22%22%2C%22url%22%3A%22https%3A%2F%2Fapi.github.com%2Fusers%2Fchronosllc0-ai%22%2C%22html_url%22%3A%22https%3A%2F%2Fgithub.com%2Fchronosllc0-ai%22%2C%22followers_url%22%3A%22https%3A%2F%2Fapi.github.com%2Fusers%2Fchronosllc0-ai%2Ffollowers%22%2C%22following_url%22%3A%22https%3A%2F%2Fapi.github.com%2Fusers%2Fchronosllc0-ai%2Ffollowing%7B%2Fother_user%7D%22%2C%22gists_url%22%3A%22https%3A%2F%2Fapi.github.com%2Fusers%2Fchronosllc0-ai%2Fgists%7B%2Fgist_id%7D%22%2C%22starred_url%22%3A%22https%3A%2F%2Fapi.github.com%2Fusers%2Fchronosllc0-ai%2Fstarred%7B%2Fowner%7D%7B%2Frepo%7D%22%2C%22subscriptions_url%22%3A%22https%3A%2F%2Fapi.github.com%2Fusers%2Fchronosllc0-ai%2Fsubscriptions%22%2C%22organizations_url%22%3A%22https%3A%2F%2Fapi.github.com%2Fusers%2Fchronosllc0-ai%2Forgs%22%2C%22repos_url%22%3A%22https%3A%2F%2Fapi.github.com%2Fusers%2Fchronosllc0-ai%2Frepos%22%2C%22events_url%22%3A%22https%3A%2F%2Fapi.github.com%2Fusers%2Fchronosllc0-ai%2Fevents%7B%2Fprivacy%7D%22%2C%22received_events_url%22%3A%22https%3A%2F%2Fapi.github.com%2Fusers%2Fchronosllc0-ai%2Freceived_events%22%2C%22type%22%3A%22User%22%2C%22user_view_type%22%3A%22public%22%2C%22site_admin%22%3Afalse%7D%2C%22body%22%3A%22%23%23%23+Motivation%5Cn-+Provide+rollout+safety+and+observability+for+channel+tooling+so+staged+enabling+of+high-risk+interactive+features+is+possible.+%5Cn-+Ensure+runtime+controls+%28mode+changes%2C+auto-mode+send+blocking%29+are+measurable+for+diagnostics+and+operator+visibility.+%5Cn-+Prevent+chat+pollution+from+low-level+browser%2Fworkflow+execution+steps+and+add+focused+regression+coverage+for+these+behaviors.+%5Cn%5Cn%23%23%23+Description%5Cn-+Added+a+lightweight+in-memory+telemetry+collector+%60RuntimeTelemetry%60+in+%60backend%2Fruntime_telemetry.py%60+to+track+%60control_mode_changes%60%2C+%60auto_mode_blocked_sends%60%2C+%60channel_tool_success%60%2C+%60channel_tool_failure%60%2C+and+per-platform+breakdowns+with+%60snapshot%28%29%60+output.+%5Cn-+Introduced+rollout+feature+flags+via+%60backend%2Fintegrations%2Ffeature_flags.py%60+and+new+settings+%60CHANNEL_TOOLS_TELEGRAM_ADVANCED_ENABLED%60%2C+%60CHANNEL_TOOLS_SLACK_ADVANCED_ENABLED%60%2C+and+%60CHANNEL_TOOLS_DISCORD_ADVANCED_ENABLED%60+in+%60config.py%60%2C+and+applied+gating+with+graceful+fallbacks+in+%60integrations%2Ftelegram.py%60%2C+%60integrations%2Fslack_connector.py%60%2C+and+%60integrations%2Fdiscord.py%60.+%5Cn-+Wired+telemetry+into+runtime+flows+in+%60main.py%60+so+that+%60_send_channel_text%60+records+channel+tool+outcomes%2C+%60_apply_runtime_mode_update%60+records+mode+changes%2C+and+disabled+runtime-control+actions+record+blocked-send+events%3B+admin+runtime+snapshot+now+exposes+telemetry.+%5Cn-+Added+a+browser%2Fworkflow+noise+filter+in+%60main.py%60+%28%60_is_browser_chat_pollution%60%29+to+avoid+persisting+browser+primitive+and+workflow-step+noise+into+user-facing+chat+history+while+still+streaming+steps+to+the+frontend.+%5Cn-+Added+regression+tests+and+updates%3A+%60tests%2Ftest_runtime_telemetry.py%60%2C+feature-flag+tests+in+%60tests%2Ftest_slack_discord_adapters.py%60+and+%60tests%2Ftest_telegram.py%60%2C+and+runtime%2Fcontrol%2Fchat-pollution+tests+in+%60tests%2Ftest_main_websocket.py%60%2C+plus+a+subagent+steering+payload+test+in+%60tests%2Ftest_mode_commands.py%60.+%5Cn%5Cn%23%23%23+Testing%5Cn-+Built+frontend+with+%60npm+run+-w+frontend+build%60+and+the+build+completed+successfully.+%5Cn-+Ran+a+targeted+WebSocket+smoke+test+with+%60pytest+-q+tests%2Ftest_main_websocket.py%3A%3Atest_websocket_navigate_smoke%60+which+passed.+%5Cn-+Executed+the+targeted+regression+test+subset+for+telemetry%2C+feature+flags%2C+runtime+controls%2C+and+browser-noise+behavior+with+%60pytest%60+against+the+new%2Fupdated+tests+%28%60tests%2Ftest_runtime_telemetry.py%60%2C+%60tests%2Ftest_main_websocket.py%60+checks%2C+%60tests%2Ftest_slack_discord_adapters.py%60%2C+%60tests%2Ftest_telegram.py%60%2C+%60tests%2Ftest_mode_commands.py%60%29+and+those+focused+tests+passed.+%5Cn-+Note%3A+%60python+-m+py_compile+main.py+backend%2Fpydantic_adk_runner.py%60+was+attempted+but+could+not+complete+because+%60backend%2Fpydantic_adk_runner.py%60+is+not+present+in+this+repository%3B+%60main.py%60+compiles+otherwise.%5Cn%5Cn------%5Cn%5BCodex+Task%5D%28https%3A%2F%2Fchatgpt.com%2Fcodex%2Fcloud%2Ftasks%2Ftask_e_69e21c66b1348326b60298d680b0f568%29%22%2C%22created_at%22%3A%222026-04-17T11%3A50%3A04Z%22%2C%22updated_at%22%3A%222026-04-17T12%3A12%3A43Z%22%2C%22closed_at%22%3Anull%2C%22merged_at%22%3Anull%2C%22merge_commit_sha%22%3A%22cc8fc22acefe9dc9292c2f67259c4778f0c9bc4e%22%2C"
)

def main():
    # Step 1: Extract payload value (strip "payload=" prefix)
    if encoded_payload.startswith("payload="):
        encoded_data = encoded_payload[8:]  # Remove "payload="
    else:
        encoded_data = encoded_payload

    # Step 2: URL-decode the payload
    decoded_json_str = urllib.parse.unquote(encoded_data)

    # Step 3: Parse JSON
    payload = json.loads(decoded_json_str)

    # Step 4: Display comprehensive breakdown
    print("=" * 70)
    print("GITHUB WEBHOOK PAYLOAD ANALYSIS")
    print("=" * 70)

    # --- Event Metadata ---
    print("\n" + "=" * 70)
    print("EVENT METADATA")
    print("=" * 70)

    pr = payload.get("pull_request", {})
    action = payload.get("action", "N/A")
    print(f"Event Type: pull_request")
    print(f"Action: {action}")
    print(f"PR Number: #{pr.get('number', 'N/A')}")
    print(f"PR ID: {pr.get('id', 'N/A')}")
    print(f"Node ID: {pr.get('node_id', 'N/A')}")

    # Timestamps
    created = pr.get('created_at', 'N/A')
    updated = pr.get('updated_at', 'N/A')
    closed = pr.get('closed_at', 'N/A')
    merged = pr.get('merged_at', 'N/A')
    print(f"Created At: {created}")
    print(f"Updated At: {updated}")
    print(f"Closed At: {closed or 'N/A (still open)'}")
    print(f"Merged At: {merged or 'N/A (not merged yet)'}")

    # --- Repository Information ---
    print("\n" + "=" * 70)
    print("REPOSITORY INFORMATION")
    print("=" * 70)

    # Extract repo info from PR base/head or from other fields if available
    base = pr.get('base', {})
    head = pr.get('head', {})
    base_repo = base.get('repo', {}) if isinstance(base, dict) else {}
    head_repo = head.get('repo', {}) if isinstance(head, dict) else {}

    print(f"Base Branch: {base.get('label', 'N/A') if isinstance(base, dict) else 'N/A'}")
    print(f"Head Branch: {head.get('label', 'N/A') if isinstance(head, dict) else 'N/A'}")
    print(f"Base Repo: {base_repo.get('full_name', 'N/A')}")
    print(f"Head Repo: {head_repo.get('full_name', 'N/A')}")
    print(f"Base Repo URL: {base_repo.get('html_url', 'N/A')}")
    print(f"Head Repo URL: {head_repo.get('html_url', 'N/A')}")

    # --- Pull Request Details ---
    print("\n" + "=" * 70)
    print("PULL REQUEST DETAILS")
    print("=" * 70)

    print(f"Title: {pr.get('title', 'N/A')}")
    print(f"State: {pr.get('state', 'N/A')}")
    print(f"Locked: {pr.get('locked', False)}")
    print(f"Draft: {pr.get('draft', False)}")

    # URLs
    print(f"\nAPI URL: {pr.get('url', 'N/A')}")
    print(f"HTML URL: {pr.get('html_url', 'N/A')}")
    print(f"Diff URL: {pr.get('diff_url', 'N/A')}")
    print(f"Patch URL: {pr.get('patch_url', 'N/A')}")
    print(f"Issue URL: {pr.get('issue_url', 'N/A')}")

    # Commit info
    commit_count = pr.get('commits', 'N/A')
    additions = pr.get('additions', 'N/A')
    deletions = pr.get('deletions', 'N/A')
    changed_files = pr.get('changed_files', 'N/A')
    print(f"\nCommits: {commit_count}")
    print(f"Additions: {additions}")
    print(f"Deletions: {deletions}")
    print(f"Changed Files: {changed_files}")

    # Maintainer can edit?
    print(f"Maintainer Can Edit: {pr.get('maintainer_can_edit', 'N/A')}")

    # --- User / Sender Information ---
    print("\n" + "=" * 70)
    print("USER / SENDER INFORMATION")
    print("=" * 70)

    user = pr.get('user', {})
    print(f"Login: {user.get('login', 'N/A')}")
    print(f"User ID: {user.get('id', 'N/A')}")
    print(f"Node ID: {user.get('node_id', 'N/A')}")
    print(f"Type: {user.get('type', 'N/A')}")
    print(f"Site Admin: {user.get('site_admin', False)}")
    print(f"Avatar URL: {user.get('avatar_url', 'N/A')}")
    print(f"Profile URL: {user.get('html_url', 'N/A')}")
    print(f"GitHub URL: {user.get('url', 'N/A')}")

    # --- PR Body Content ---
    print("\n" + "=" * 70)
    print("PR BODY CONTENT")
    print("=" * 70)
    body = pr.get('body', '')
    if body:
        # Decode any remaining URL-encoded characters
        decoded_body = urllib.parse.unquote(body)
        print(decoded_body)
    else:
        print("(No body content)")

    # --- Labels, Assignees, Reviewers ---
    print("\n" + "=" * 70)
    print("LABELS, ASSIGNEES & REVIEWERS")
    print("=" * 70)

    labels = pr.get('labels', [])
    print(f"Labels ({len(labels)}):")
    for label in labels:
        print(f"  - {label.get('name', 'N/A')} (color: {label.get('color', 'N/A')})")

    assignees = pr.get('assignees', [])
    print(f"\nAssignees ({len(assignees)}):")
    for assignee in assignees:
        print(f"  - {assignee.get('login', 'N/A')}")

    requested_reviewers = pr.get('requested_reviewers', [])
    print(f"\nRequested Reviewers ({len(requested_reviewers)}):")
    for reviewer in requested_reviewers:
        print(f"  - {reviewer.get('login', 'N/A')}")

    # --- Merge Status & Additional Metadata ---
    print("\n" + "=" * 70)
    print("MERGE STATUS & ADDITIONAL METADATA")
    print("=" * 70)

    print(f"Mergeable: {pr.get('mergeable', 'N/A')}")
    print(f"Mergeable State: {pr.get('mergeable_state', 'N/A')}")
    print(f"Merged: {pr.get('merged', False)}")
    print(f"Rebaseable: {pr.get('rebaseable', 'N/A')}")
    print(f"Squashable: {pr.get('squashable', 'N/A')}")
    print(f"Merge Commit SHA: {pr.get('merge_commit_sha', 'N/A')}")
    print(f"Head SHA: {pr.get('head', {}).get('sha', 'N/A') if isinstance(head, dict) else 'N/A'}")

    # --- Raw keys (for completeness) ---
    print("\n" + "=" * 70)
    print("TOP-LEVEL PAYLOAD KEYS")
    print("=" * 70)
    print(f"Keys: {list(payload.keys())}")

    print("\n" + "=" * 70)
    print("DECODE & PARSE COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
