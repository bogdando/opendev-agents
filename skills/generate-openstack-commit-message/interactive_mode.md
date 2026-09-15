# Interactive Mode Workflow

Detailed workflow for interactive mode - asks 9 questions ONE AT A TIME about metadata tags.

## Critical Rule

**ONE QUESTION AT A TIME** - Never ask multiple questions in a single message. Wait for the user's response before proceeding to the next question.

## Question Sequence

### Question 1: Component prefix

"Would you like to add a component prefix to the subject line? (e.g., 'tests:', 'api:', or leave blank)"

**Wait for response.** If they provide one, update the subject line with the prefix.

---

### Question 2: Bug references

"Does this change fix or relate to any bugs? (Provide bug number or 'no')"

**Wait for response.** If yes, ask follow-up:

"Is it fully fixed, partially fixed, or just related? (full/partial/related)"

**Wait for response.** Add appropriate tag:
- Full fix: `Closes-Bug: #1234567`
- Partial fix: `Partial-Bug: #1234567`
- Related: `Related-Bug: #1234567`

---

### Question 3: Documentation impact

"Does this change affect documentation or require doc updates? (yes/no)"

**Wait for response.** If yes, add `DocImpact`

---

### Question 4: API impact

"Does this change modify any public HTTP APIs? (yes/no)"

**Wait for response.** If yes, add `APIImpact`

---

### Question 5: Security impact

"Does this change have security implications? (yes/no)"

**Wait for response.** If yes, ask follow-up:

"Do you need to add a detailed security explanation? (yes/no)"

**Wait for response.**

If yes to detailed:
- Ask: "Please provide the security impact explanation:"
- **Wait for their explanation text**
- Add as:
  ```
  SecurityImpact:
  
  [Their explanation with 72-char wrapping]
  ```

If no to detailed:
- Just add `SecurityImpact` flag

---

### Question 6: Upgrade impact

"Will this affect upgrades or require special upgrade steps? (yes/no)"

**Wait for response.** If yes:

"Please provide the upgrade impact explanation:"

**Wait for their explanation text.** Add as:
```
UpgradeImpact:

[Their explanation with 72-char wrapping]
```

---

### Question 7: Co-authors

"Did anyone else contribute to this change? (Provide 'Name <email>' or 'no')"

**Wait for response.** If yes:
- Add `Co-Authored-By: Name <email>`
- Then ask: "Any other co-authors? (Provide 'Name <email>' or 'no')"
- **Wait for response**
- Repeat until they say no

---

### Question 8: Additional sign-offs

"Does anyone else need to sign off on this change? (Provide 'Name <email>' or 'no')"

**Wait for response.** If yes:
- Add `Signed-off-by: Name <email>` (after the primary sign-off)
- Then ask: "Any other sign-offs? (Provide 'Name <email>' or 'no')"
- **Wait for response**
- Repeat until they say no

---

### Question 9: Test Plan

"Would you like to include a Test Plan section? (yes/no)"

**Wait for response.** If yes:

"Please provide the test plan (you can list multiple items):"

**Wait for their test plan.** Add it before metadata tags:
```
Test Plan:
- Test item 1
- Test item 2
- Test item 3
```

---

## After All Questions

Assemble the complete message with all gathered metadata in the correct order (see formatting_rules.md for tag order).

Show the message and ask: "How does this look? Would you like me to adjust anything?"

## Interactive Mode Rules

1. **One question at a time**: Never ask multiple questions in a single message
2. **Wait for response**: After each question, stop and wait for user to answer
3. **Skip if not applicable**: If user says "no" or "skip", move to next question immediately
4. **Be conversational**: Keep questions simple and friendly
5. **Show progress**: Optionally mention "Question X of 9" to show progress
6. **Allow skipping all**: User can say "skip rest" to jump to final message generation
7. **Track answers**: Remember responses as you build up the metadata
