# Production Deployment Rollback

**Firm:** Larkspur Cloud Partners
**Salesforce area:** Release management
**Owner:** Idris Venkataram
**Last reviewed:** 2025-04-22

## Time Estimates

- Hands-on time: 75 minutes
- Monitoring window: 2 hours

## Purpose

Restores production to the last known good state when a release causes a business-critical defect. It sets out the decision, the technical reversal and the communication so the client is back in service quickly.

## Prerequisites

- The last known good release tag or change set is identified
- The delivery manager has approved a rollback after a Priority 1 or Priority 2 incident
- A backup export of any data changed by the release exists
- System Administrator access to production and to the source repository

## Procedure

1. Open an incident and record the failing behaviour, the release number and the time first noticed.
   - Verification: The incident ticket holds all three details.
2. Get written rollback approval from the delivery manager and the client business owner.
   - Verification: Both approvals are attached to the ticket.
3. Freeze all other deployments and user changes to production metadata.
   - Verification: The freeze message is posted and acknowledged in the project channel.
4. Deactivate new Flows, triggers and validation rules that cause the defect.
   - Verification: The Setup pages show the items as Inactive and the defect no longer reproduces.
5. Validate the previous release against production with RunLocalTests.
   - Verification: The validation result shows Succeeded.
6. Deploy the previous release and delete the components that exist only in the failed release using a destructive changes manifest.
   - Verification: The Deployment Status shows Succeeded with 0 failures.
7. Repair data changed by the failed release from the backup export where the client approves it.
   - Verification: Spot-checked rows match the backup values.
8. Run the smoke tests and keep a 2 hour monitoring window with the incident channel open.
   - Verification: All smoke tests pass and no new incidents are raised in the 2 hour window.

## Rollback Steps

If the rollback itself goes wrong:

1. If the rollback deployment fails, deploy the metadata in smaller groups starting with fields and objects.
2. If data repair fails, stop and restore the affected object from the backup export in a controlled load.
3. Escalate to the chief technology officer if the previous release cannot be validated.
4. Keep the freeze in place until the cause of the failed release is documented.

## Known Issues

| Symptom | Resolution |
|---|---|
| Destructive deployment fails with 'Cannot delete custom field: field is referenced in a Flow' | Deactivate and delete the Flow version that uses the field, then repeat the destructive deployment. |
| Validation fails with 'Test failure: FIELD_CUSTOM_VALIDATION_EXCEPTION' | Temporarily deactivate the validation rule named in the error, deploy and reactivate it after the release. |
| Component 'cannot be deleted because it has been modified since the deployment: Active Flow version' | Make the previous Flow version active in the Flow Builder first and then delete the failed version. |
