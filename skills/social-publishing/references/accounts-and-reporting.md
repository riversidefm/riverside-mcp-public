# Accounts and reporting

## Connect an account

Offer this for a platform that is not connected, or whose connection returns
`INVALID_TOKEN` or `UNAUTHORIZED`, instead of sending the user to the web app.

1. `social_connect_social_account(platform, studioId, studioSlug,
   productionId, …)` returns a link. The slug is where the browser lands
   afterwards, so it must be this studio's own.
2. Show the link and ask the user to say when they have approved on the
   platform's page. Nothing is connected until then. There is no waiting tool,
   and calling again only mints a new link.
3. `social_get_connected_platforms(studioId)` and report the account that was
   not in the returned `connectedPlatformAccountIds`. If that list is null,
   do not guess: list what is connected and ask which one they added.

## Disconnect an account

`social_disconnect_social_account(studioId, platformAccountId, productionId)`
cancels every upload still scheduled on that account, and on Facebook detaches
every Page under the same login. Name the account, say that first, and get an
explicit yes.

## How a published post is doing

`social_get_upload_analytics(uploadId, studioId, …)` answers for one post;
`social_list_uploads` with `includeViews` covers several. Always pass
`studioId`, so a missing analytics permission is detected; offer to reconnect
on `MISSING_ANALYTICS_SCOPE`. The numbers are collected on a schedule: relay
`asOf`, and read `hasData`, `frozen`, and `reasonCode` before quoting
anything. Report `series` values as given; never add or subtract them.
