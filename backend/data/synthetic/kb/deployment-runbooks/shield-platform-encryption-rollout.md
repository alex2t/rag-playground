# Shield Platform Encryption Rollout

**Firm:** Larkspur Cloud Partners
**Salesforce area:** Shield
**Owner:** Wilhelmina Oyelaran
**Last reviewed:** 2025-06-24

## Purpose

Enables Shield Platform Encryption on the approved list of fields in a production org and confirms that search, reports and integrations still work. It also sets key management and backup so that data remains available.

## Time Required

- Hands-on time: 190 minutes
- Monitoring window: 72 hours

## Prerequisites

- Shield licences are purchased and the Shield Platform Encryption permission is granted to the administrator.
- The list of up to 20 fields to encrypt is approved by the client security contact.
- A tenant secret backup and key rotation procedure is agreed with the client.
- The Encryption Policy impact check has been run in a sandbox.
- Integrations, reports and SOQL queries that use the fields have been listed.
- A change window outside business hours is booked.

## Steps

1. Review the field list against the data classification sheet.
   - Verify: Every field in the list has an approved classification.
2. Deploy the same encryption settings to a Full sandbox and run the Encryption Statistics page.
   - Verify: Statistics show no blocked fields.
3. Run the report, list view and SOQL tests that use the sandbox encrypted fields.
   - Verify: Each test returns the expected results or a documented limitation.
4. In production, open Platform Encryption and generate the tenant secret.
   - Verify: The tenant secret appears with an Active status.
5. Download and store the tenant secret backup in the approved key vault.
   - Verify: A key vault entry exists and a second person confirms access.
6. Assign the Manage Encryption Keys permission to the named key custodians.
   - Verify: Only the named users appear in the permission set assignment list.
7. Select the first batch of 10 fields in Encryption Policy and choose the deterministic or probabilistic scheme as approved.
   - Verify: The policy page lists the 10 fields as selected.
8. Save the policy and start the background encryption of existing data.
   - Verify: The Encryption Statistics page shows the job as In Progress.
9. Wait for the encryption job to finish.
   - Verify: The statistics page shows 100 percent of existing data encrypted for the first batch.
10. Repeat the selection for the remaining approved fields in a second batch.
    - Verify: The statistics page shows Complete for every approved field.
11. Run the production smoke tests on reports, search and the integrations listed.
    - Verify: All smoke tests pass or show only documented limitations.
12. Check the Setup Audit Trail and Event Monitoring for the encryption changes.
    - Verify: The log shows each change made by the named administrator.
13. Start the 72 hour monitoring window and review integration error logs every 12 hours.
    - Verify: The review log has an entry for each 12 hour check.
14. Close the window and report the status to the client security contact.
    - Verify: The security contact confirms receipt of the report.

## Rollback Steps

1. Stop any running encryption job by contacting Salesforce Support if it cannot be cancelled in Setup.
2. Remove the affected fields from the Encryption Policy and save, then start decryption of existing data.
3. Wait for the statistics page to show the fields as not encrypted.
4. Restore any integration settings that were changed for encrypted fields.
5. Keep the tenant secret backup until the client security contact confirms it can be retired.

## Known Issues

### Field cannot be encrypted

- **Symptom:** Field selection fails with 'This field cannot be encrypted because it is used in a unique or external ID setting'
- **Resolution:** Remove the unique or external ID setting, or choose the deterministic scheme where the field type allows it.

### Report filter error

- **Symptom:** Reports return 'Error: Filtering on an encrypted field uses a probabilistic scheme'
- **Resolution:** Switch the field to the deterministic scheme or remove the filter from the report.

### SOQL field not filterable

- **Symptom:** SOQL fails with 'INVALID_FIELD: field is not filterable' on an encrypted field
- **Resolution:** Remove the field from the WHERE or ORDER BY clause and apply the filter in code.

### Insufficient storage

- **Symptom:** Encryption job shows 'Failed: Insufficient storage while re-encrypting data'
- **Resolution:** Free data storage or buy more, then restart the encryption job.
