# Permission Set and Permission Set Group Change

| Field | Value |
|---|---|
| Firm | Larkspur Cloud Partners |
| Document type | Deployment runbook |
| Salesforce area | Security and access |
| Owner | Keiko Lindqvist |
| Last reviewed | 2025-01-27 |
| Hands-on time | 60 minutes |
| Monitoring window | 48 hours |

## Purpose

Applies approved changes to permission sets and permission set groups so users gain or lose access in a controlled way. It reduces the risk of over-permissioning and of broken access to key objects after a release.

## Prerequisites

- A signed access change request listing users, permission sets and the reason for the change
- The permission set changes have been tested in a sandbox with a representative user
- The access matrix document is up to date
- System Administrator access to production

## Steps

1. Compare the requested access with the current access matrix.
   - Verification: Each requested change is mapped to a named permission set in the matrix.
2. Make the changes in the sandbox permission set and permission set group and recalculate the group.
   - Verification: The group status shows Updated, not Updating or Failed.
3. Log in as a test user in the sandbox and test each object and field affected.
   - Verification: The test log shows access granted or removed as requested.
4. Deploy the permission set metadata to production through the agreed deployment method.
   - Verification: The Deployment Status shows Succeeded.
5. Assign or remove the permission set group for the listed users using a bulk assignment.
   - Verification: The Assigned Users list matches the access change request.
6. Run a SOQL query on PermissionSetAssignment for the affected users.
   - Verification: The query results agree with the request line by line.
7. Start a 48 hour monitoring window and review the Login History and support requests for access errors.
   - Verification: No insufficient access errors are raised by affected users in the 48 hour window.

## Rollback

1. Remove the new permission set group assignments for the affected users.
2. Reassign the previous permission set group to the affected users.
3. Deploy the previous permission set metadata version from source control.
4. Ask two affected users to confirm that their earlier access is restored.

## Known Issues

| Symptom | Resolution |
|---|---|
| Assignment fails with 'INSUFFICIENT_ACCESS_OR_READONLY' for a user | The user licence does not allow the permissions in the set; assign a compatible licence or remove the incompatible permission. |
| Group status stays at Updating for more than 30 minutes | Open the group, choose Recalculate and wait for Updated; if it fails, edit the group again and save. |
| Deployment error 'You cannot assign a permission set that has the Modify All Data permission to this user profile' | Remove the broad permission from the set or move the user to a profile that supports it after client approval. |
