# Revenue Cloud Pricing Rule Release

| Field | Value |
|---|---|
| Firm | Larkspur Cloud Partners |
| Salesforce area | Revenue Cloud |
| Owner | Gideon Rasmussen |
| Last reviewed | 2025-03-31 |
| Hands-on time | 155 minutes |
| Monitoring window | 36 hours |

## Purpose

Releases new or changed price books, pricing rules and discount schedules to production without disturbing open quotes. It uses test quotes with known expected prices to confirm that the pricing logic is correct.

## Prerequisites

- The finance stakeholder has signed off the new price lists and discount policy.
- A pricing test sheet lists at least 25 scenarios with the expected net price.
- The pricing rules are deployed to a sandbox and all scenarios pass.
- A list of open quotes affected by the change has been produced.

## Steps

1. Export the current price books, pricing rules and discount schedules from production.
   - Verification: The export files are stored on the project drive with counts noted.
2. Deploy the pricing rule metadata to production using the Salesforce CLI Metadata Deployment from Source Control runbook.
   - Verification: The deployment shows Succeeded.
3. Load the new price book entries with an upsert on the external ID.
   - Verification: The success file count equals the number of entries in the new price list.
4. Activate the new price book and set the effective date.
   - Verification: The price book shows Active with the right effective date.
5. Create test quotes for each of the 25 scenarios in the pricing test sheet.
   - Verification: Each quote net price matches the expected value to the cent.
6. Test each approval path with a quote that crosses the discount threshold.
   - Verification: The quote routes to the named approver.
7. Generate the quote document in each of the 2 templates.
   - Verification: The documents show correct totals, tax lines and terms.
8. Review the open quotes in the affected list.
   - Verification: Each open quote keeps its original price or is flagged for repricing as agreed.
9. Delete the test quotes created for validation.
   - Verification: A query for quotes with the test prefix returns 0 rows.
10. Begin the 36 hour monitoring window and review new quotes and approval requests each morning.
    - Verification: No quote shows a price different from the price list by more than the approved discount.

## Rollback Steps

1. Deactivate the new price book and reactivate the previous one.
2. Deactivate the new pricing rules.
3. Reload the exported price book entries and rules from the backup files.
4. Reprice any quotes created during the faulty period with the finance stakeholder.
5. Notify the sales operations users of the restored prices.

## Known Issues

### Quote line shows 'Error: Price book entry not found for product and currency'

Resolution: Add the missing price book entry for the product in the quote currency and recalculate the quote.

### Approval submit fails with 'No approver found for the approval step'

Resolution: Assign an approver or a queue to the approval step and resubmit the quote.

### Calculation fails with 'Apex CPU time limit exceeded' on large bundles

Resolution: Reduce the number of nested price rules on the bundle or split the bundle and recalculate.
