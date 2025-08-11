#!/bin/bash

# Mojolicious Template Formatter API Script with Authentication
# Usage: ./format_mojolicious_auth.sh [OPTIONS]
# 
# Options:
#   -u, --url URL          API base URL (default: http://localhost:8000)
#   -t, --token TOKEN      API token (overrides .env and environment)
#   -r, --remove-empty     Remove empty lines from output
#   -f, --file FILE        Read input from file instead of heredoc
#   -o, --output FILE      Write output to file instead of stdout
#   -h, --help             Show this help message
#
# Authentication:
#   The script automatically looks for API tokens in this order:
#   1. Command line --token option
#   2. .env file (FLASK_API_TOKEN=...)
#   3. Environment variable FLASK_API_TOKEN
#   4. Environment variable API_TOKEN

set -euo pipefail

# Default values
API_URL="http://localhost:8000"
API_TOKEN=""
REMOVE_EMPTY=false
INPUT_FILE=""
OUTPUT_FILE=""

# Function to show help
show_help() {
    cat << EOF
Mojolicious Template Formatter API Script with Authentication

Usage: $0 [OPTIONS]

Options:
    -u, --url URL          API base URL (default: http://localhost:8000)
    -t, --token TOKEN      API token (overrides .env and environment)
    -r, --remove-empty     Remove empty lines from output
    -f, --file FILE        Read input from file instead of heredoc
    -o, --output FILE      Write output to file instead of stdout
    -h, --help             Show this help message

Authentication:
    The script automatically looks for API tokens in this order:
    1. Command line --token option
    2. .env file (FLASK_API_TOKEN=...)
    3. Environment variable FLASK_API_TOKEN
    4. Environment variable API_TOKEN

Examples:
    # Format heredoc (uses token from .env or environment)
    $0

    # Format with specific token
    $0 --token your_api_token_here

    # Format with empty line removal
    $0 --remove-empty

    # Format from file
    $0 --file template.ep

    # Format and save to file
    $0 --file input.ep --output formatted.ep

    # Use different API URL
    $0 --url https://your-server.com

    # Format heredoc inline
    $0 <<< '<% my \$name = "World"; %><h1>Hello <%= \$name %>!</h1>'

Environment Setup:
    Create a .env file with:
    FLASK_API_TOKEN=your_token_here

    Or set environment variable:
    export FLASK_API_TOKEN=your_token_here
EOF
}

# Function to load API token from .env file
load_token_from_env() {
    local env_file=".env"
    
    # Look for .env in current directory first
    if [[ -f "$env_file" ]]; then
        # Read FLASK_API_TOKEN from .env file
        local token
        token=$(grep "^FLASK_API_TOKEN=" "$env_file" 2>/dev/null | cut -d'=' -f2- | tr -d '"' | tr -d "'")
        if [[ -n "$token" ]]; then
            echo "$token"
            return 0
        fi
    fi
    
    # Look for .env in script directory
    local script_dir
    script_dir=$(dirname "$(readlink -f "$0")")
    env_file="$script_dir/.env"
    
    if [[ -f "$env_file" ]]; then
        local token
        token=$(grep "^FLASK_API_TOKEN=" "$env_file" 2>/dev/null | cut -d'=' -f2- | tr -d '"' | tr -d "'")
        if [[ -n "$token" ]]; then
            echo "$token"
            return 0
        fi
    fi
    
    return 1
}

# Function to get API token from various sources
get_api_token() {
    # 1. Use command line token if provided
    if [[ -n "$API_TOKEN" ]]; then
        echo "$API_TOKEN"
        return 0
    fi
    
    # 2. Try to load from .env file
    local token
    if token=$(load_token_from_env); then
        echo "$token"
        return 0
    fi
    
    # 3. Try environment variable FLASK_API_TOKEN
    if [[ -n "${FLASK_API_TOKEN:-}" ]]; then
        echo "$FLASK_API_TOKEN"
        return 0
    fi
    
    # 4. Try environment variable API_TOKEN
    if [[ -n "${API_TOKEN:-}" ]]; then
        echo "$API_TOKEN"
        return 0
    fi
    
    # No token found
    return 1
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -u|--url)
            API_URL="$2"
            shift 2
            ;;
        -t|--token)
            API_TOKEN="$2"
            shift 2
            ;;
        -r|--remove-empty)
            REMOVE_EMPTY=true
            shift
            ;;
        -f|--file)
            INPUT_FILE="$2"
            shift 2
            ;;
        -o|--output)
            OUTPUT_FILE="$2"
            shift 2
            ;;
        -h|--help)
            show_help
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            echo "Use --help for usage information" >&2
            exit 1
            ;;
    esac
done

# Get API token
if ! API_TOKEN=$(get_api_token); then
    cat << EOF >&2
Error: No API token found!

The script needs an API token for authentication. Please provide one using:

1. Command line option:
   $0 --token your_token_here

2. .env file in current or script directory:
   echo "FLASK_API_TOKEN=your_token_here" > .env

3. Environment variable:
   export FLASK_API_TOKEN=your_token_here

To generate a new token, run:
   cd /path/to/your/flask/app
   python3 website_fixed_auth.py --genenv

EOF
    exit 1
fi

# Function to format text via API with authentication
format_text() {
    local input_text="$1"
    local api_endpoint="${API_URL}/api/format"
    
    # Prepare JSON payload
    local json_payload
    json_payload=$(jq -n \
        --arg text "$input_text" \
        --argjson remove_empty "$REMOVE_EMPTY" \
        '{text: $text, remove_empty: $remove_empty}')
    
    # Make authenticated API request
    local response
    response=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer $API_TOKEN" \
        -d "$json_payload" \
        "$api_endpoint")
    
    # Check for errors
    local error
    error=$(echo "$response" | jq -r '.error // empty')
    if [[ -n "$error" ]]; then
        case "$error" in
            "Invalid origin"|"Invalid CSRF token"|"Invalid API token"|"Invalid token"|"Unauthorized")
                echo "Authentication Error: $error" >&2
                echo "Please check your API token and try again." >&2
                echo "Use --help for authentication setup instructions." >&2
                ;;
            "Rate limit exceeded")
                echo "Rate Limit Error: $error" >&2
                echo "Please wait a moment and try again." >&2
                ;;
            *)
                echo "API Error: $error" >&2
                ;;
        esac
        exit 1
    fi
    
    # Extract formatted text
    echo "$response" | jq -r '.formatted_text'
}

# Validate API token format (basic check)
if [[ ! "$API_TOKEN" =~ ^[a-fA-F0-9]{40}$ ]]; then
    echo "Warning: API token format looks unusual (expected 40 hex characters)" >&2
    echo "Token: ${API_TOKEN:0:10}..." >&2
fi

# Get input text
if [[ -n "$INPUT_FILE" ]]; then
    # Read from file
    if [[ ! -f "$INPUT_FILE" ]]; then
        echo "Error: File '$INPUT_FILE' not found" >&2
        exit 1
    fi
    input_text=$(cat "$INPUT_FILE")
elif [[ ! -t 0 ]]; then
    # Read from stdin/pipe
    input_text=$(cat)
else
    # Interactive heredoc input
    echo "Enter your Mojolicious template code (end with Ctrl+D):"
    input_text=$(cat)
fi

# Check if input is empty
if [[ -z "${input_text// }" ]]; then
    echo "Error: No input provided" >&2
    exit 1
fi

# Validate input size (client-side check)
input_length=${#input_text}
if [[ $input_length -gt 10000 ]]; then
    echo "Error: Input too large ($input_length characters, max 10,000)" >&2
    exit 1
fi

# Format the text
echo "Formatting $input_length characters..." >&2
formatted_text=$(format_text "$input_text")

# Output result
if [[ -n "$OUTPUT_FILE" ]]; then
    echo "$formatted_text" > "$OUTPUT_FILE"
    echo "Formatted text saved to: $OUTPUT_FILE" >&2
else
    echo "$formatted_text"
fi

echo "Formatting completed successfully." >&2