# Record-Triggered Flow Deployment and Activation

| Field | Value |
|---|---|
| Firm | Larkspur Cloud Partners |
| Salesforce area | Flow and automation |
| Owner | Calista Brandt |
| Last reviewed | 2025-01-15 |
| Hands-on time | 45 minutes |
| Monitoring time | 0 hours |

## Purpose

Deploys a tested Flow to production and activates it in a controlled way. It checks that the Flow version is correct and faults are visible to administrators from the moment it goes live.

## Prerequisites

- The Flow has passed bulk testing with 200 rows in a sandbox.
- A fault path with an email alert to the admin group is configured.
- The Flow is deployed as inactive so that activation is a separate deliberate action.

## Deployment and Activation Steps

1. Deploy the Flow metadata to production as an inactive version.
   - Verification: The Deployment Status shows Succeeded and the Flow shows Inactive in Setup.
2. Review the entry criteria and the fault path in Flow Builder.
   - Verification: The entry criteria match the design document and the fault path sends to the admin group.
3. Run the Flow debug with one test row in production using rollback mode.
   - Verification: The debug output shows the expected path and no rows are saved.
4. Activate the new Flow version.
   - Verification: The version shows Active and the previous version is Obsolete.
5. Create or update one test row that meets the entry criteria.
   - Verification: The expected field updates and related rows appear on the test row.
6. Delete the test row and confirm the fault email address receives nothing.
   - Verification: No fault email is received and the row is in the recycle bin.

## Rollback Steps

1. Open the Flow in Setup and activate the previous version.
2. Deactivate the new version if there is no previous version.
3. Correct data changed by the Flow using the backup report.

## Known Issues

### Required field missing

- **Symptom:** Flow fails with 'FIELD_CUSTOM_VALIDATION_EXCEPTION: Required field missing'
- **Resolution:** Populate the required field in the Flow or add an entry condition so the Flow does not run on incomplete data.

### Too many SOQL queries

- **Symptom:** Error 'Too many SOQL queries: 101' during a bulk update
- **Resolution:** Move Get Records elements outside loops and use collections, then redeploy.

### Activation blocked by unconnected element

- **Symptom:** Activation blocked with 'This flow version cannot be activated: a required element is not connected'
- **Resolution:** Connect the unlinked element in Flow Builder and save before activating.
