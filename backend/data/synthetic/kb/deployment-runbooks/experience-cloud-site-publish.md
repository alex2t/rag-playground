# Experience Cloud Site Publish

**Firm:** Larkspur Cloud Partners
**Salesforce area:** Experience Cloud
**Owner:** Saoirse Kettleby
**Last reviewed:** 2025-02-26

## Purpose

Publishes a new or updated Experience Cloud site to production and confirms that sharing, branding and self-service pages work for each portal user type. It also protects client data by checking visibility settings before the site is open to external users.

## Time Required

- Hands-on time: 110 minutes
- Monitoring window: 12 hours

## Prerequisites

- The site metadata has been deployed to production
- Guest user and external user sharing rules are reviewed by the security lead
- The accessibility check against WCAG 2.1 AA is passed
- Test portal users exist for each user type
- The custom domain and certificate are configured where a client domain is used

## Procedure

1. Open Experience Builder in production and confirm the site template and theme are the release version.
   - Verification: The version label in Builder matches the release number.
2. Review the guest user profile and sharing rules.
   - Verification: The guest user has no access to objects outside the approved list.
3. Log in as each test portal user type and visit every page template.
   - Verification: Each user sees only the data allowed by the sharing model.
4. Submit a test case through the self-service case form.
   - Verification: The case is created in the org with the correct owner and portal user.
5. Test the knowledge search with 5 typical questions.
   - Verification: Each search returns the expected published article.
6. Test the self-registration and password reset flows.
   - Verification: The test user receives the email and can log in.
7. Click Publish in Experience Builder.
   - Verification: The confirmation email arrives and the site status shows Live.
8. Load the public URL in a private browser window.
   - Verification: The page loads over HTTPS with the correct branding and no mixed content warnings.
9. Hold a 12 hour monitoring window and check Login History and the site's error pages.
   - Verification: No repeated login or sharing errors appear in the 12 hour window.

## Rollback Steps

1. Unpublish the site by setting its status to Inactive in Workspaces.
2. Disable self-registration so that no new external users are created.
3. Restore the previous published site version from the Builder publish history.
4. Post a maintenance message on the client's main website where requested.

## Known Issues

### Insufficient Privileges error

- **Symptom:** Users see 'Insufficient Privileges: You don't have the level of access necessary'
- **Resolution:** Check the sharing set or sharing rule for the user's account and give read access to the object.

### Publish validation error

- **Symptom:** Publish fails with 'The site could not be published because of a validation error on a page'
- **Resolution:** Open the page named in the error, fix the invalid component property and publish again.

### Guest access to component not allowed

- **Symptom:** Guest users see the error 'Your organization does not allow guest access to this component'
- **Resolution:** Add the guest profile to the component's visibility settings or remove the component from the public page.
