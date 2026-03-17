#!/bin/bash
set -euo pipefail

# ── Aegis Railway Deployment ──────────────────────────────────────────
# Prerequisites:
#   - Railway CLI installed (npm i -g @railway/cli)
#   - Logged in: railway login
#   - Project linked: railway link
#
# Required environment variables (set via Railway dashboard or CLI):
#   DATABASE_URL          - PostgreSQL connection string (Railway Postgres plugin)
#   SESSION_SECRET        - Random string for session signing
#   ENCRYPTION_SECRET     - Random string for BYOK key encryption
#   GEMINI_API_KEY        - Default Gemini API key (optional if users BYOK)
#
# Optional:
#   OPENAI_API_KEY, ANTHROPIC_API_KEY, MISTRAL_API_KEY, GROQ_API_KEY
#   GOOGLE_OAUTH_CLIENT_ID, GOOGLE_OAUTH_CLIENT_SECRET
#   GITHUB_OAUTH_CLIENT_ID, GITHUB_OAUTH_CLIENT_SECRET

echo "🚀 Deploying Aegis to Railway..."

# Check Railway CLI
if ! command -v railway &> /dev/null; then
    echo "❌ Railway CLI not found. Install with: npm i -g @railway/cli"
    exit 1
fi

# Verify login
railway whoami || {
    echo "❌ Not logged in. Run: railway login"
    exit 1
}

echo "📦 Building and deploying..."
railway up --detach

echo ""
echo "============================================"
echo "🎯 Aegis Deployment Triggered"
echo ""
echo "  Check status:   railway status"
echo "  View logs:       railway logs"
echo "  Open dashboard:  railway open"
echo ""
echo "  Remember to add a PostgreSQL plugin and"
echo "  set environment variables in the dashboard."
echo "============================================"
