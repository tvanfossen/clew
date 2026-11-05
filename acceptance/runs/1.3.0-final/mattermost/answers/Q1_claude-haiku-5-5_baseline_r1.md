**Short answer:** a failed post is kept locally and marked as failed. It is not retried automatically at all: there is one `createPost` attempt per send. Retrying happens only when the user taps "Try Again", which calls `retryFailedPost`.

**1. What happens on failure** (`app/actions/remote/post.ts`, `createPost`, ~lines 153–199)

- The post is written to the local database before the network call, under a `pending_post_id`, so it shows in the UI immediately.
- If `client.createPost` throws, the post is re-saved with `props.failed = true`. It stays in the channel with the failed state.
- Three server errors are the exception and remove the post instead: `DELETED_ROOT_POST_ERROR`, `TOWN_SQUARE_READ_ONLY_ERROR`, and `PLUGIN_DISMISSED_POST_ERROR`.
- A `BOR_DENIED_BY_POLICY_ERROR` also expires the cached render-permission entry for the channel, but the post is still kept as failed.

**2. Automatic retries: none**

- Nothing in the send path loops or re-queues. I found no retry counter, backoff, or reconnect-triggered resend for posts.
- `app/managers/redaction_revalidation_manager.ts:241` says so explicitly: "No retry loop: it would spin while offline. A failed post offers the user a retry."
- The only automatic handling in `createPost` is a dedupe guard (~line 93): if a non-failed post already exists under the same pending ID, it returns without sending. That prevents duplicates, not retries.

**3. What a retry does** (`retryFailedPost`, `post.ts` ~lines 228–307)

- Triggered from the failed-post UI, `app/components/post_list/post/body/failed/index.tsx:48` ("Try Again", testID `post.failed.retry`).
- Clears `props.failed` and sets `update_at` to now, so the post goes back to the pending state in the UI. `create_at` is reset to now in the request body.
- Captures the redaction epoch, then calls `client.createPost` once.
- On success, it upserts the server-returned post and updates the channel's last-post timestamp (unless it is a CRT reply).
- On failure, it applies the same rules as above: the three removal errors delete the post, and anything else sets `failed` back to true. The user can tap again.