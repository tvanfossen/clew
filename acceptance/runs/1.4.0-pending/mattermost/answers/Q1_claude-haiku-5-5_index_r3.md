A failed new post is kept locally and marked as failed. It is not retried automatically. The app makes exactly one send attempt, and only a manual "Try Again" sends it again.

**1. The first failure (`createPost`, `app/actions/remote/post.ts:74`)**

- Before the network call, the post is written to the local WatermelonDB with a temporary `pending_post_id` and an id equal to it, so it shows in the UI immediately.
- If `client.createPost` throws, the handler logs the error and then branches on the server error ID:
  - **Root post deleted, Town Square read-only, or plugin-dismissed post:** the local post is removed (`removePost`). It is not kept as failed.
  - **Any other error:** the post is re-saved with `props.failed = true`. If CRT is enabled, its thread record is created too. The function returns `{data: true}`, so the caller treats it as handled.
  - **Burn-on-read policy denial:** the cached render-permission entry for the channel is expired as well.

**2. Automatic retries: zero**

- `ClientPosts.createPost` (`app/client/rest/posts.ts:43-47`) passes `noRetry: true`.
- In `app/client/rest/tracking.ts:383-385`, that sets `retryPolicyConfiguration = {retryLimit: 0}`.
- The network manager's default policy would otherwise retry 3 times with exponential backoff (`app/managers/network_manager.ts:68-71`). The post send opts out of that.
- Nothing else in the send path re-queues a failed post. A grep for retry logic found none.

**3. What "Try Again" does (`retryFailedPost`, `app/actions/remote/post.ts:228`)**

It is triggered from the failed-post sheet (`app/components/post_list/post/body/failed/index.tsx:46-49`). It does not go through `createPost`:

1. Clears `props.failed` and bumps `update_at`. The original `create_at` is kept.
2. Calls `client.createPost` again with the same content, plus a fresh `create_at`.
3. On success, it writes the server post and updates the channel's last-post time (unless the post is a CRT reply).
4. On failure it sets `failed: true` again, or removes the post for the same three error IDs as above. It makes one attempt per tap, with no loop.

The failed-post sheet also offers "Delete Message", which calls `removePost`.

**Note on the UI:** `isPostFailed` (`app/utils/post/index.ts:97-99`) treats a still-pending post as failed once it is older than `POST_TIME_TO_FAIL`, which is 10 seconds (`app/constants/post.ts:57`). So a request that hangs, with no error thrown, also shows the failed icon. Its `failed` prop is never set in that case.

I did not verify how the server-side post record replaces the local pending record after a successful retry. The `retryFailedPost` success path writes the new post but does not explicitly delete the old pending row.