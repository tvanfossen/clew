A failed post stays on screen, marked as failed. It is not retried automatically, and "Try Again" resends the same post.

1. **Failure handling** (`app/actions/remote/post.ts:154-198`): `createPost` makes one `client.createPost` call. On error it logs the failure and writes the post locally with `props.failed: true`, keeping the pending ID. The post remains visible in the channel. The exceptions are three server errors (deleted root post, Town Square read-only, plugin-dismissed post), where the post is removed from the database instead.

2. **Automatic retries: none.** The network layer is configured with exponential retry and `retryLimit: 3` (`app/managers/network_manager.ts:68-70`). But `client.createPost` passes `noRetry: true` (`app/client/rest/posts.ts:46`), which sets `retryLimit: 0` (`app/client/rest/tracking.ts:383-384`). So a failed send gets one attempt and no automatic resend.

3. **Manual retry** (`retryFailedPost`, `post.ts:228-307`): the failed post's bottom sheet has a "Try Again" action (`app/components/post_list/post/body/failed/index.tsx:46-49`) that calls this. It:
   - Clears `props.failed` and refreshes `update_at` so the UI shows the post as pending again.
   - Sends the post to the server again. The `create_at` timestamp is kept from the original attempt.
   - On success, writes the server's post to the database, replacing the local placeholder.
   - On failure, marks the post failed again, or removes it for the same three server errors.

   It is a single attempt per tap, and the user can tap again. The other option on that sheet, "Delete Message", removes the post.