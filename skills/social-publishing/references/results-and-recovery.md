# Results and recovery

Outcome interpretation, retry admissibility, and error-specific recovery after a
publish is processing, partial, or failed, or after a timeout, transport failure,
missing result, or any other unknown outcome. The main skill file's safety
contract still governs every follow-up here.

## Classify the outcome

- **Processing or accepted for later completion:** explain that processing is
  underway and the post should follow automatically. Relay a returned
  user-facing message when present; do not expose a raw internal status or
  resend the call.
- **Timeout, transport failure, missing response, or unknown result:** say that
  submission could have happened but cannot be confirmed. Stop. A call that
  returned nothing yielded no `uploadId` to read back, so with no idempotency
  key, retrying could duplicate a live post.
- **Explicit per-target failure:** fetch fresh platform guidance and evaluate
  the retry gate below. A failure on one target does not undo or change another
  target's result.

## Retry gate

A retry is admissible only when both the returned failure and current
`social_get_publishing_guidelines` recovery guidance explicitly establish that
no post was created and that retrying this failure is safe. Never retry a
success, processing result, partial or ambiguous result, timeout, transport
failure, or unknown outcome.

Passing this gate makes a retry eligible; it does not authorize the call. Return
to the main preview and obtain the required new confirmation, whether or not the
payload changed. If the same explicit failure repeats after one clean retry,
stop and report the platform's result.

## Error-specific recovery

Use the fresh live guidance for the failure in hand rather than a remembered
error-code catalogue.

- **Export required:** re-run the main routing table; this outcome matches its
  scheduling-and-draft-export row, which supplies current compose choices.
  Retry only if the explicit failure passes the retry gate, and return to the
  main preview because the payload changed.
- **Metadata or media rejected:** correct only what the live guidance and
  returned failure identify, then return to the main preview and confirmation.
- **YouTube copyright / Content-ID signal:** use video-editing's
  `editing_get_export_publish_data` to inspect the edit's media and surface a
  flagged match instead of retrying over it.
