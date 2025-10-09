#!/usr/bin/env bash
set -euo pipefail

# Example launch script for the MCP Filter proxy
# This demonstrates using environment variables instead of CLI args

export MF_TRANSPORT=stdio
export MF_STDIO_COMMAND="npx"
export MF_STDIO_ARGS="-y @supabase/mcp-server-supabase@latest --access-token YOUR_TOKEN"
export MF_ALLOW_TOOLS="execute_sql,list_tables,get_project"
export MF_LOG_LEVEL=INFO

# Optional settings (uncomment to use)
# export MF_RENAME_PREFIX="supabase_"
# export MF_INCLUDE_HEALTH_TOOL=1
# export MF_SHOW_TOKEN_ESTIMATES=1

mcp-filter run "$@"
