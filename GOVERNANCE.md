# Governance

## Branches

- `main`: protected release history
- `agent/<description>`: implementation branches
- Changes enter `main` through pull requests after Tester evidence

## Required gates

1. Builder runs tests and attaches evidence.
2. Tester verifies DoD independently.
3. Article-related changes include fixture tests for wrong numbers, stale timestamps, unsupported news causation and chart mismatch.
4. Release checks secrets, licenses and documentation.
5. Publishing analysis content still requires Article QA PASS and user approval.

## Escalation

Internal issues go to CC for up to three decision rounds per issue ID. If unresolved after round three, stop and ask the user. Cross-team, scope, budget, security, deletion and external-publication issues go to the user immediately through CC.

## Repository visibility

Private by default. Changing visibility requires explicit user approval.
