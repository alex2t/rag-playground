# MuleSoft API Deployment to Production

| Item | Detail |
|---|---|
| Firm | Larkspur Cloud Partners |
| Salesforce area | MuleSoft |
| Owner | Lorcan Mulvihill |
| Last reviewed | 2025-06-03 |
| Hands-on time | 280 minutes |
| Monitoring window | 48 hours |

## Purpose

This runbook promotes a tested MuleSoft API application from the staging environment to production in Anypoint Platform and connects it to the live back-office systems. It also applies the security policies needed to expose the API safely to Salesforce.

## Prerequisites

- MuleSoft Anypoint licences cover a production vCore for the application.
- The API specification is published in Anypoint Exchange and approved by the client technical contact.
- Staging end-to-end tests have passed with 0 critical defects.
- Production credentials for each connected system are stored in the secure properties vault.
- A technical contact is available at each connected system during the deployment window.
- Monitoring alerts are configured in Anypoint Monitoring.

## Deployment Steps

1. Tag the application code in the repository with the release number.
   - Verification: The tag is visible in the remote repository and the build pipeline starts.
2. Run the build pipeline to produce the deployable JAR with MUnit tests.
   - Verification: The pipeline shows all MUnit tests passing and test coverage of at least 80 percent.
3. Update the production properties file with production endpoints and secure property keys.
   - Verification: A configuration diff against staging shows only environment values that differ.
4. Deploy the application to the production environment in Runtime Manager.
   - Verification: The application status shows Running with a green health indicator.
5. Run a health check call against the API's status endpoint.
   - Verification: The endpoint returns HTTP 200 with the expected version number.
6. Apply the client ID enforcement and rate limiting policies in API Manager.
   - Verification: A call without credentials returns HTTP 401.
7. Test the throttling policy by sending 120 calls in one minute.
   - Verification: Calls above the limit return HTTP 429.
8. Update the Salesforce named credential to use the production API URL.
   - Verification: A test callout from Salesforce returns HTTP 200.
9. Run one end-to-end business scenario with real test data across Salesforce and the back-office system.
   - Verification: The data appears correctly in both systems.
10. Enable the production alerts for error rate, response time and CPU.
    - Verification: A forced test alert is delivered to the on-call email list.
11. Begin the 48 hour monitoring window and check Anypoint Monitoring dashboards every 4 hours on the first day.
    - Verification: The check log has an entry for each scheduled review.
12. Hold a handover call with the client technical contact and share the monitoring dashboard link.
    - Verification: The contact confirms access to the dashboard.
13. Close the 48 hour window and record error rate and average response time in the release file.
    - Verification: The release file shows both figures.

## Rollback Steps

1. Switch the Salesforce named credential back to the previous endpoint or to a maintenance responder.
2. Stop the new application version in Runtime Manager.
3. Redeploy the previous application version from Anypoint Exchange.
4. Remove the new policy version in API Manager and reapply the previous one.
5. Run the health check and one end-to-end scenario on the restored version.
6. Notify the client technical contact and the connected system owners.

## Known Issues

### Deployment stays in 'Deploying' and then fails with 'Application deployment timed out'

Check that the vCore allocation is available and that the secure properties key matches, then redeploy.

### Calls return 'HTTP 503 Service Unavailable' from the API gateway

Confirm the application is Running and has healthy workers; restart the application if a worker is stuck.

### Log shows 'javax.net.ssl.SSLHandshakeException: PKIX path building failed'

Import the connected system's certificate chain into the application truststore and redeploy.
