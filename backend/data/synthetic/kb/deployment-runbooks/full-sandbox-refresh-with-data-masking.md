# Full Sandbox Refresh with Data Masking

**Firm:** Larkspur Cloud Partners
**Salesforce area:** Sandbox management
**Owner:** Dashiell Pruitt
**Last reviewed:** 2025-03-18

## Purpose

Refreshes a Full sandbox from production and ensures client data is masked before any developer or tester can see it. It keeps the sandbox usable for the next release cycle and meets the firm's data security rule on masking.

## Effort

- Hands-on time: 95 minutes
- Monitoring time: 0 hours

## Prerequisites

- At least 29 days have passed since the previous Full sandbox refresh.
- A SandboxPostCopy Apex class that masks personal data has been tested in a Partial sandbox.
- A change freeze has been agreed with the client business owner.
- A list of named credentials and external endpoints that must be re-pointed after the refresh is available.
- System Administrator access to production and to the sandbox.

## Procedure

1. Announce a change freeze to all developers and testers at least 2 business days before the refresh date.
   - **Verification:** Every developer has acknowledged the freeze message in the project channel.
2. Export sandbox-only configuration that is not in source control, such as custom setting values and email templates.
   - **Verification:** The exported file row counts match the counts shown in the sandbox before the refresh.
3. In Setup, open Sandboxes, choose Refresh on the Full sandbox and select the SandboxPostCopy class in the Apex class field.
   - **Verification:** The sandbox status changes to Pending and then Processing.
4. Wait for the sandbox refresh completion email sent to the System Administrator.
   - **Verification:** The sandbox status shows Completed and the completion email has arrived.
5. Log in to the refreshed sandbox and query Contact email addresses and phone numbers.
   - **Verification:** No email address is outside the example.invalid domain and no phone number matches a production value.
6. Re-point named credentials and external endpoints to the client's test systems.
   - **Verification:** A test callout from Developer Console returns HTTP 200 from each test endpoint.
7. Reload the exported sandbox-only configuration.
   - **Verification:** Row counts after the load match the counts from the export file.
8. Set Email Deliverability to System email only and lift the change freeze.
   - **Verification:** Setup shows the Access level as System email only and the lift message is posted to the project channel.

## Rollback

1. If masking has not run, immediately set Email Deliverability to No access and revoke sandbox logins for all users except the System Administrator.
2. Delete the refreshed sandbox and re-create it from the sandbox clone taken before the refresh, if one exists.
3. Re-run the SandboxPostCopy class manually from Developer Console and repeat the masking verification query.
4. Keep the change freeze in place and notify the client business owner of the new availability date.

## Known Issues

### Refresh button is greyed out

- **Symptom:** Refresh button is greyed out with the message 'You can refresh this sandbox in 14 days'
- **Resolution:** The Full sandbox refresh interval has not passed; wait for the date shown or use a Partial sandbox for the work.

### SandboxPostCopy fails with a DML row limit error

- **Symptom:** SandboxPostCopy fails with 'System.LimitException: Too many DML rows: 10001'
- **Resolution:** Rewrite the masking class to run as a Batchable with a scope of 200 and re-run it from Developer Console.

### Named credential callout is unauthorized

- **Symptom:** Named credential callout returns 'CalloutException: Unauthorized endpoint'
- **Resolution:** Add the test endpoint URL to Remote Site Settings or to the named credential and retry the callout.
