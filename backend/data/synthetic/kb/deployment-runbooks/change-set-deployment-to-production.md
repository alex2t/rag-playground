# Change Set Deployment to Production

**Firm:** Larkspur Cloud Partners
**Salesforce area:** Metadata deployment
**Owner:** Tobias Wainwright
**Last reviewed:** 2025-02-11

## Purpose

Moves a defined group of metadata components from a sandbox to production using an outbound change set. It is used by smaller releases where the client does not run source control.

## Time Required

- Hands-on time: 120 minutes
- Monitoring window: 24 hours

## Prerequisites

- A deployment connection is authorised between the sandbox and production.
- The change set contents have been approved by the client business owner.
- All Apex tests in the sandbox pass with at least 85 percent coverage on the changed classes.
- A deployment window of at least 90 minutes is booked outside client peak hours.

## Deployment Steps

1. Create an outbound change set named with the release number and add each approved component.
   - Verify: The component list matches the release checklist item for item.
2. Use View/Add Dependencies to add any missing dependent components.
   - Verify: The dependency list shows no unresolved components.
3. Upload the change set to the production org.
   - Verify: The status shows Uploaded and an inbound change set appears in production.
4. In production, run Validate on the inbound change set with the RunLocalTests option.
   - Verify: The validation result shows Succeeded with all tests passing.
5. Capture the validation ID and screenshot the test results for the release file.
   - Verify: The release file contains the validation ID and the screenshot.
6. Deploy the validated inbound change set inside the agreed window.
   - Verify: The Deployment Status page shows Succeeded with 0 component failures.
7. Run the smoke test script covering the changed page layouts, fields and automation.
   - Verify: All smoke test cases are marked passed by the tester.
8. Post the deployment outcome to the project channel and start the 24 hour monitoring window.
   - Verify: The Setup Audit Trail shows only the expected changes and the channel post is visible.
9. Check Apex Exception Emails and Debug Logs at the end of the 24 hour monitoring window.
   - Verify: No new unhandled exceptions are listed for the deployed components.

## Rollback Steps

1. Stop any further changes to production and notify the client business owner.
2. Reverse the change by building an outbound change set from the sandbox state before the release.
3. Deactivate any deployed Flow or Apex trigger manually in production if it causes errors.
4. Redeploy the earlier change set, validate it and deploy it in a new window.
5. Record the failure cause in the release file for the post-release review.

## Known Issues

### Average test coverage error

- **Symptom:** Deployment fails with 'Average test coverage across all Apex Classes and Triggers is 74%, at least 75% Apex code coverage is required'
- **Resolution:** Add test classes for the uncovered classes in the sandbox, upload a new change set and validate again.

### Component in use error

- **Symptom:** Error 'Cannot delete component: in use by another component'
- **Resolution:** Change sets cannot delete components, so remove the reference first and delete the component manually in production after the deployment.

### Upload not visible in production

- **Symptom:** Upload is not visible in production and the inbound list is empty
- **Resolution:** Wait up to 30 minutes for the upload to be processed and confirm the deployment connection is authorised in both orgs.
