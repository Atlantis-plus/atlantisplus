#!/bin/bash

# Company Search Comparison Test: OpenAI vs Claude
# Tests search functionality across both chat endpoints

# Configuration
API_URL="http://localhost:8000"
TOKEN="eyJhbGciOiJFUzI1NiIsImtpZCI6ImQ3ZGNjNWExLTFhNWItNDA5MS05MTJmLWY4ZjMwOTIyMTg1NyIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJodHRwczovL21oZHBva2lnYnBybm53bXNnenV5LnN1cGFiYXNlLmNvL2F1dGgvdjEiLCJzdWIiOiJkYWY4MDJlMS1jYzI3LTQ0MWYtYmJlMy1hZmJhMjQ0OTFjMGMiLCJhdWQiOiJhdXRoZW50aWNhdGVkIiwiZXhwIjoxNzcxMDcwNzI3LCJpYXQiOjE3NzEwNjcxMjcsImVtYWlsIjoidGdfMTIzNDU2QGF0bGFudGlzLmxvY2FsIiwicGhvbmUiOiIiLCJhcHBfbWV0YWRhdGEiOnsicHJvdmlkZXIiOiJlbWFpbCIsInByb3ZpZGVycyI6WyJlbWFpbCJdfSwidXNlcl9tZXRhZGF0YSI6eyJkaXNwbGF5X25hbWUiOiJUZXN0IFVzZXIiLCJlbWFpbF92ZXJpZmllZCI6dHJ1ZSwiaXNfdGVzdF91c2VyIjp0cnVlLCJ0ZWxlZ3JhbV9pZCI6MTIzNDU2LCJ0ZWxlZ3JhbV91c2VybmFtZSI6InRlc3RfdXNlciJ9LCJyb2xlIjoiYXV0aGVudGljYXRlZCIsImFhbCI6ImFhbDEiLCJhbXIiOlt7Im1ldGhvZCI6InBhc3N3b3JkIiwidGltZXN0YW1wIjoxNzcxMDY3MTI3fV0sInNlc3Npb25faWQiOiI5MzE4NzQzZC01ZDIxLTRkNTQtODgyNC03OGY4YmY2ZDhjMWYiLCJpc19hbm9ueW1vdXMiOmZhbHNlfQ.bBxqaFgE-WJ7CUVRl2a6YMQExFAXh2diJn3XpK5jJORKo0-bonwSBDfxtsZcN9CatmALUmfoGRagn6fG-gKo-Q"

# Test queries
QUERIES=(
    "кто работает в Google?"
    "кто из Yandex?"
    "найди людей из ByteDance"
    "кто из Тинькофф?"
)

# Output file
OUTPUT_FILE="/Users/evgenyq/Projects/atlantisplus/service/tests/company_search_results.md"

# Initialize output
echo "# Company Search Test Results" > "$OUTPUT_FILE"
echo "" >> "$OUTPUT_FILE"
echo "**Test Date:** $(date)" >> "$OUTPUT_FILE"
echo "**Server:** $API_URL" >> "$OUTPUT_FILE"
echo "" >> "$OUTPUT_FILE"
echo "---" >> "$OUTPUT_FILE"
echo "" >> "$OUTPUT_FILE"

# Function to test endpoint
test_endpoint() {
    local endpoint=$1
    local query=$2
    local endpoint_name=$3

    echo "Testing: $endpoint_name with query: $query"

    # Make request and save full response
    response=$(curl -s -X POST "$API_URL$endpoint" \
        -H "Authorization: Bearer $TOKEN" \
        -H "Content-Type: application/json" \
        -d "{\"message\": \"$query\"}")

    echo "$response"
}

# Run tests for each query
for query in "${QUERIES[@]}"; do
    echo "" >> "$OUTPUT_FILE"
    echo "## Query: \"$query\"" >> "$OUTPUT_FILE"
    echo "" >> "$OUTPUT_FILE"

    # Test OpenAI endpoint
    echo "### OpenAI (/chat)" >> "$OUTPUT_FILE"
    echo '```json' >> "$OUTPUT_FILE"
    openai_response=$(test_endpoint "/chat" "$query" "OpenAI")
    echo "$openai_response" | jq '.' >> "$OUTPUT_FILE" 2>&1 || echo "$openai_response" >> "$OUTPUT_FILE"
    echo '```' >> "$OUTPUT_FILE"
    echo "" >> "$OUTPUT_FILE"

    # Wait to avoid rate limiting
    sleep 2

    # Test Claude endpoint
    echo "### Claude (/chat/claude)" >> "$OUTPUT_FILE"
    echo '```json' >> "$OUTPUT_FILE"
    claude_response=$(test_endpoint "/chat/claude" "$query" "Claude")
    echo "$claude_response" | jq '.' >> "$OUTPUT_FILE" 2>&1 || echo "$claude_response" >> "$OUTPUT_FILE"
    echo '```' >> "$OUTPUT_FILE"
    echo "" >> "$OUTPUT_FILE"

    # Wait between queries
    sleep 2

    echo "---" >> "$OUTPUT_FILE"
    echo "" >> "$OUTPUT_FILE"
done

echo ""
echo "Test completed! Results saved to: $OUTPUT_FILE"
