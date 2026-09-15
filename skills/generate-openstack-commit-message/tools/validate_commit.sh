#!/bin/bash
# Validates OpenStack commit message format
# Returns: 0 on success, non-zero with errors on failure

message="$1"
errors=()

# Extract subject (first line)
subject=$(echo "$message" | head -1)

# Check subject length
if [ ${#subject} -gt 50 ]; then
    errors+=("Subject exceeds 50 characters (${#subject})")
fi

# Check for period at end
if [[ "$subject" =~ \\.$ ]]; then
    errors+=("Subject ends with period")
fi

# Check blank line after subject
line2=$(echo "$message" | sed -n '2p')
if [ -n "$line2" ]; then
    errors+=("Missing blank line after subject")
fi

# Check body line lengths
while IFS= read -r line; do
    if [ ${#line} -gt 72 ]; then
        errors+=("Body line exceeds 72 characters: ${line:0:50}...")
    fi
done < <(echo "$message" | tail -n +3)

# Check required tags
if ! echo "$message" | grep -q "Assisted-By:"; then
    errors+=("Missing Assisted-By tag")
fi

if ! echo "$message" | grep -q "Signed-off-by:"; then
    errors+=("Missing Signed-off-by tag")
fi

# Report errors or success
if [ ${#errors[@]} -gt 0 ]; then
    echo "Validation failed:"
    printf '  - %s\n' "${errors[@]}"
    exit 1
else
    exit 0
fi
