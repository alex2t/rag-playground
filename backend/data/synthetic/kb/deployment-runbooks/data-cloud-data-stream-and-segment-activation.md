# Data Cloud Data Stream and Segment Activation

**Firm:** Larkspur Cloud Partners
**Salesforce area:** Data Cloud
**Document owner:** Naveen Castellanos
**Last reviewed:** 2025-06-17

## Purpose

This runbook moves a validated Data Cloud configuration into production and activates the first live segments to a destination. It confirms that ingestion, identity resolution and activation work end to end on real client data.

## Time Required

- Hands-on time: 170 minutes
- Monitoring window: 24 hours

## Prerequisites

- Data Cloud is provisioned in the client's production org.
- Each source system has a named data owner and a connection that can be used in production.
- The data model mapping document and identity resolution ruleset are approved.
- The activation destination credentials are available.
- Data Cloud users hold the right Data Cloud permission sets.

## Deployment Steps

1. Package the data streams, mappings and calculated insights and deploy them to production.
   - **Verify:** The deployment shows Succeeded and each stream appears in Data Cloud.
2. Create the source connections in production using the production credentials.
   - **Verify:** Each connection test shows Connected.
3. Start ingestion of each data stream with the scheduled frequency.
   - **Verify:** Each stream shows a Successful last run with a nonzero row count.
4. Compare the ingested row counts with the source system counts.
   - **Verify:** Counts agree within the 0.5 percent tolerance in the mapping document.
5. Check the field mappings in the data model for each stream.
   - **Verify:** No required field shows unmapped.
6. Run the identity resolution ruleset job.
   - **Verify:** The job status shows Completed and unified profiles are created.
7. Review a sample of 30 unified profiles for merge accuracy.
   - **Verify:** At least 28 of the 30 profiles are merged correctly.
8. Refresh the calculated insights and check the values for 5 known customers.
   - **Verify:** The values match the expected figures in the test sheet.
9. Publish the segments and review the populations.
   - **Verify:** Each segment population is within 5 percent of the expected count.
10. Activate the segments to the agreed destination.
    - **Verify:** The activation status shows Success and the destination receives the audience.
11. Begin the 24 hour monitoring window and review stream refresh results and activation status at 8 hour intervals.
    - **Verify:** Every scheduled refresh in the window shows Successful.

## Rollback Steps

1. Pause the activation to the destination.
2. Stop the scheduled refresh of the new data streams.
3. Delete the segments and activations created by the release.
4. Delete the data streams that were created and any unified profiles built from them.
5. Repeat the validation in a sandbox before trying again.

## Known Issues

| Symptom | Resolution |
|---|---|
| Data stream refresh fails with 'Error: Invalid credentials for the connector' | Update the connection credentials with the data owner and run the refresh again. |
| Identity resolution job shows 'Failed: matching rule has no valid fields' | Map the matching fields to the unified Individual model and run the job again. |
| Activation fails with 'Destination authentication expired' | Reauthorise the destination connection and trigger the activation again. |
