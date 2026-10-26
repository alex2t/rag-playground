# Salesforce CLI Metadata Deployment from Source Control

| Field | Value |
|---|---|
| Firm | Larkspur Cloud Partners |
| Salesforce area | Metadata deployment |
| Owner | Julien Archambault |
| Last reviewed | 2025-04-02 |
| Hands-on time | 85 minutes |
| Monitoring window | 4 hours |

## Purpose

Deploys tagged source from the Git repository to a target org using the Salesforce CLI with a validated quick deploy. It gives a repeatable and auditable path for client projects that use source control.

## Prerequisites

- Salesforce CLI is installed and updated to the version listed in the project repository.
- The release branch is merged and tagged with the release number.
- The target org is authorised with an alias using the JWT flow or web login.
- A package manifest file lists every component in the release.
- Apex tests for the changed classes pass in a scratch org or sandbox.

## Deployment Steps

1. Check out the release tag and confirm the working tree is clean.
   - Verification: git status reports nothing to commit and the tag name matches the release number.
2. Run sf org list and confirm the target alias is connected.
   - Verification: The target alias shows Connected with the expected username.
3. Retrieve the current production metadata for the manifest into a temporary folder.
   - Verification: The retrieve command returns Succeeded and the folder contains the manifest components.
4. Compare the retrieved metadata with the release source to identify unintended changes.
   - Verification: The diff shows only the components in the release checklist.
5. Run sf project deploy start with the --dry-run flag, the manifest and the RunLocalTests test level.
   - Verification: The output shows Status Succeeded with all tests passing.
6. Note the validated job ID from the dry run output.
   - Verification: The job ID is recorded in the release file.
7. Run sf project deploy quick with the validated job ID inside the deployment window.
   - Verification: The command returns Succeeded and the Deployment Status page agrees.
8. Run the automated smoke test suite against the target org.
   - Verification: The suite finishes with 0 failures.
9. Start a 4 hour monitoring window and watch Apex Exception Emails and the Event Log.
   - Verification: No new exception emails are received for the deployed components.
10. Tag the deployment in the Git repository with the date and the target alias.
    - Verification: The tag is visible in the remote repository.
11. Close the 4 hour monitoring window and post the summary to the project channel.
    - Verification: The summary post lists the job ID and the test results.

## Rollback Steps

1. Stop further deployments and notify the delivery manager.
2. Check out the previous release tag in the repository.
3. Run a validate-only deployment of the previous tag with RunLocalTests.
4. Quick deploy the validated previous release job to restore the earlier metadata.
5. Manually remove any new components that the previous tag does not contain using a destructive changes manifest.

## Known Issues

### Quick deploy fails with 'The validation ID is not valid or has expired'

A validation is usable for 10 days only after it succeeds; run the dry run again and quick deploy the new job ID.

### Deploy fails with 'INVALID_CROSS_REFERENCE_KEY: invalid cross reference id'

A referenced profile, queue or user does not exist in the target org; add the missing component to the manifest or create it first.

### Command returns 'ERROR running project deploy start: expired access/refresh token'

Log in to the org again with sf org login jwt or web and rerun the command.

### Test failure 'System.LimitException: Too many SOQL queries: 101'

Bulkify the failing Apex code, move queries outside loops and run the tests again.
