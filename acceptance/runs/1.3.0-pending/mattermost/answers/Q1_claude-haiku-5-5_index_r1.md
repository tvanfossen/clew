**Short answer:** A failed post stays in the local database, marked as failed. It is never retried automatically. The user retries it by hand with "Try Again", and each tap makes one send attempt.

**What happens on failure** (`createPost` in `app/actions/remote/post.ts:74-226`)

- The post is written locally before the network call, with its pending ID (`${currentUserId}:${timestamp}`) and no server ID yet, so it shows in the UI right away.
- If `client.createPost` throws, the post is kept with `props.failed = true`. The one exception is three server errors (deleted root post, Town Square read-only, plugin-dismissed post), where the post is removed instead.
- A `BOR_DENIED_BY_POLICY_ERROR` also expires the cached render-permission entry for the channel.

**How many automatic retries**

- Zero. The app's network client defaults to 3 retries with exponential backoff (`app/managers/network_manager.ts:68-73`), but `ClientPosts.createPost` passes `noRetry: true` (`app/client/rest/posts.ts:43-47`), which sets `retryLimit: 0` (`app/client/rest/tracking.ts:383-385`). So a failed send is not retried at the network layer either.

**What retrying does** (`retryFailedPost`, `app/actions/remote/post.ts:228-307`)

- Triggered from the failed-post button (`app/components/post_list/post/body/failed/index.tsx`), via the "Try Again" item in the bottom sheet.
- It rebuilds the post from the local record and clears `failed`. It also sets a new `create_at` and `update_at`, and the record is written back so the post shows as pending again.
- It calls `client.createPost` once. On success, the server post is stored. On failure, the post is marked `failed` again, and the same three-error removal rule applies.
- It does not go through `createPost`'s pending-ID check or re-run its file and reaction handling.

**Things to check**

- The comment in `retryFailedPost` says `create_at` stays the same as the first attempt, but the code sets `create_at: timestamp`, so the original creation time is overwritten. This looks like a code/comment mismatch.
- I did not verify how `PostModel.toApi()` carries `pending_post_id` and file IDs into the retry payload, so I can't confirm that a retried post keeps its attachments.