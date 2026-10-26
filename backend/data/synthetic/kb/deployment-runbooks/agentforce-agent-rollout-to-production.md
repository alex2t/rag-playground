# Agentforce Agent Rollout to Production

| Field | Value |
|---|---|
| Firm | Larkspur Cloud Partners |
| Salesforce area | Agentforce |
| Owner | Odalys Fenwick |
| Last reviewed | 2025-05-14 |
| Hands-on time | 210 minutes |
| Monitoring window | 72 hours |

## Purpose

This runbook moves a tested Agentforce agent from a sandbox into production and activates it for a defined user group. It ensures topics, actions and guardrails behave as designed before real customers or staff reach the agent.

## Prerequisites

- The agent passed at least 100 of the 120 scripted test conversations in the sandbox.
- Agentforce capacity is purchased and enabled in production.
- The client has approved the knowledge articles the agent relies on.
- Every Apex action and Flow used by the agent has been deployed to production.
- An escalation queue exists and is staffed during the launch week.

## Procedure

1. Freeze changes to agent topics, instructions and actions in the sandbox.
   - Verification: The agent version in the sandbox is labelled with the release number.
2. Deploy the agent metadata, topics and actions to production using the Salesforce CLI Metadata Deployment from Source Control runbook.
   - Verification: The deployment shows Succeeded with 0 component failures.
3. Confirm that the data library or knowledge source used for grounding is indexed in production.
   - Verification: A test search in the Agentforce Builder returns the expected articles.
4. Assign the Agentforce permission sets to the pilot user group.
   - Verification: The pilot users appear under Assigned Users for the permission set.
5. Run 20 smoke test conversations in the Agentforce Builder against the production configuration.
   - Verification: All 20 conversations choose the expected topic and action.
6. Test each guardrail and the escalation rule with an out-of-scope request.
   - Verification: The agent declines the request and hands off to the escalation queue.
7. Activate the agent version for the pilot user group.
   - Verification: The agent status shows Active in Setup.
8. Enable the agent in the client channel such as the Experience Cloud site or the messaging deployment.
   - Verification: A test chat from the channel reaches the agent.
9. Open the Einstein Trust Layer audit trail and confirm masking and logging are on.
   - Verification: A sample conversation appears in the audit data with masked personal values.
10. Begin the 72 hour monitoring window and review the conversation logs every 8 hours on the first day.
    - Verification: The review log has an entry for each check.
11. Review the escalation rate and the topic misses against the thresholds in the use-case brief.
    - Verification: Both measures are within the agreed thresholds or a tuning item is raised.
12. At the end of the 72 hour window, hold a go or no-go review with the client business owner.
    - Verification: The decision is recorded in the release file.

## Rollback

1. Deactivate the agent version in Setup.
2. Disable the agent in the client channel so that users see the standard contact route.
3. Remove the Agentforce permission sets from the pilot group.
4. Reactivate the previous agent version if one exists and rerun the 20 smoke tests.
5. Send a summary of failed conversations to the agent designer for tuning.

## Known Issues

### Activation fails with "Agent cannot be activated: one or more actions are missing or inactive"

Resolution: Deploy and activate the missing Flow or Apex action in production, then activate the agent again.

### Agent replies "I'm sorry, I can't help with that" to an in-scope question

Resolution: Review the topic classification description and add scope phrases, then test again with the failed utterance.

### Apex action returns "System.LimitException: Apex CPU time limit exceeded"

Resolution: Optimise the loops in the action or move the work to an asynchronous Flow.
