# Marketing Cloud Journey Activation

**Firm:** Larkspur Cloud Partners
**Salesforce area:** Marketing Cloud
**Owner:** Matthias Eklund
**Last reviewed:** 2025-05-29

## Purpose

Activates a Journey Builder journey with its audience, emails and tracking in a Marketing Cloud account. It checks consent, sender authentication and test sends so that live sends do not damage deliverability.

## Time Required

- Hands-on time: 90 minutes
- Monitoring time: 6 hours

## Prerequisites

- The sending domain passes SPF, DKIM and DMARC checks
- The subscriber list has documented consent and the unsubscribe handling is configured
- Email templates are approved by the client marketing owner
- The entry data extension is populated and the audience count is agreed

## Procedure

1. **Action:** Review the journey canvas against the journey strategy document.
   **Verification:** Each path and wait step matches the document.
2. **Action:** Check the entry data extension for subscriber keys and email addresses.
   **Verification:** A query shows 0 blank subscriber keys and 0 invalid addresses.
3. **Action:** Run Preview and Test Send on every email using 3 test subscribers.
   **Verification:** All test emails arrive with correct personalisation and a working unsubscribe link.
4. **Action:** Run the spam and rendering checks on each email.
   **Verification:** The spam score is below the agreed threshold and the layout is correct in the main email clients.
5. **Action:** Run journey validation in Journey Builder.
   **Verification:** Validation shows no errors.
6. **Action:** Activate the journey with a pilot audience of 200 subscribers.
   **Verification:** The journey status shows Running and the pilot entries are counted.
7. **Action:** Hold a 6 hour monitoring window and review bounce, unsubscribe and complaint rates before opening the full audience.
   **Verification:** The bounce rate is below 2 percent and complaints are below 0.1 percent.

## Rollback

1. Pause the journey in Journey Builder.
2. Stop any scheduled automations that feed the entry data extension.
3. Remove subscribers who have not yet entered by clearing the entry data extension.
4. Send a corrected email to affected subscribers only after client approval.

## Known Issues

| Symptom | Resolution |
|---|---|
| Activation fails with 'Journey cannot be activated: Entry Source is invalid' | Reselect the entry data extension and confirm it is sendable with the right subscriber key mapping. |
| Email send fails with 'Sender Authentication Package not configured for this send classification' | Assign the correct sender profile and delivery profile to the send classification. |
| Test send shows 'Error 5003: Email address not valid' | Correct the address format in the data extension and rerun the test send. |
