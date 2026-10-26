# Bulk Data Migration with Data Loader

**Firm:** Larkspur Cloud Partners
**Salesforce area:** Data migration
**Owner:** Thandiwe Moyo-Sinclair
**Last reviewed:** 2025-03-05

## Purpose

Loads cleansed legacy data into a Salesforce org in dependency order using Data Loader and the Bulk API. It protects data quality with load validation, reconciliation counts and a documented undo route.

## Time Required

- Hands-on time: 240 minutes
- Post-load monitoring: 8 hours

## Prerequisites

- The migration mapping workbook is approved by the client data owner.
- Source extracts are cleansed and deduplicated and stored on the firm's encrypted project drive.
- External ID fields exist on every object that receives loaded data.
- Validation rules, duplicate rules and triggers that could block the load are reviewed.
- Storage in the target org is at least 20 percent above the expected data size.

## Procedure

1. **Take a full backup export of the target objects before any load.**
   Verification: The backup files are stored on the project drive and row counts are noted.
2. **Temporarily bypass non-essential automation using the agreed custom permission or custom setting.**
   Verification: A test insert of one row creates no automation side effects.
3. **Load a pilot of 500 Account rows with upsert on the external ID.**
   Verification: The success file has 500 rows and the error file is empty.
4. **Spot-check 25 pilot Accounts against the source for field accuracy.**
   Verification: All 25 match the source values.
5. **Load the full Account set with Bulk API 2.0 and a batch size of 2,000.**
   Verification: The success file row count equals the source row count.
6. **Load Contacts using the Account external ID as the parent reference.**
   Verification: The error file is empty or holds only rows already listed as expected rejects.
7. **Load Opportunities, Cases and other child objects in the order in the mapping workbook.**
   Verification: Each child object count matches the reconciliation sheet.
8. **Re-enable the bypassed automation.**
   Verification: The custom setting or permission shows the bypass switched off.
9. **Run the reconciliation report comparing source counts to loaded counts.**
   Verification: Every object shows a variance of 0 or an approved variance.
10. **Hold an 8 hour post-load monitoring window and check for automation failures and user-reported data issues.**
    Verification: No Flow or trigger fault emails arrive for the loaded objects.

## Rollback

1. Stop all running Data Loader jobs.
2. Delete the loaded rows by their migration batch ID using a Data Loader delete job.
3. Confirm in the org that counts are back to the backup export figures.
4. Fix the source data or mapping and repeat the pilot load.
5. Notify the client data owner of the new migration date.

## Known Issues

### UNABLE_TO_LOCK_ROW

- **Symptom:** Rows fail with 'UNABLE_TO_LOCK_ROW: unable to obtain exclusive access'
- **Resolution:** Sort the file by parent ID, reduce the batch size to 200 and use serial mode, then rerun the failed rows.

### DUPLICATES_DETECTED

- **Symptom:** Rows fail with 'DUPLICATES_DETECTED'
- **Resolution:** Review the duplicate rule matches, fix the source rows or enable the bypass setting for the migration user and reload.

### STORAGE_LIMIT_EXCEEDED

- **Symptom:** Job fails with 'STORAGE_LIMIT_EXCEEDED: storage limit exceeded'
- **Resolution:** Delete test data or ask the client to purchase additional data storage before restarting the load.

### REQUEST_LIMIT_EXCEEDED

- **Symptom:** Error 'REQUEST_LIMIT_EXCEEDED: ConcurrentPerOrgLongTxn Limit exceeded'
- **Resolution:** Pause other long-running jobs and rerun the load with a smaller batch size.
