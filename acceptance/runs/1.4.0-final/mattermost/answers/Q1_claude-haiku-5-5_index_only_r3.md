**Short answer:** A failed send is kept in the local database as a visible failed post. It is not retried automatically: the send is made with zero automatic retries. A manual retry runs `retryFailedPost`, which re-sends the same post.

**1. What happens to the post on failure**

`createPost` (`app/actions/remote/post.ts:74`) first writes the post locally as a pending record, keyed by `pending_post_id`. It then calls the server. If that call throws, the catch block:

- Logs the error with `logDebug`.
- If the server error is `BOR_DENIED_BY_POLICY_ERROR`, expires the cached render-permission entry for the channel.
- If the server error is `DELETED_ROOT_POST_ERROR`, `TOWN_SQUARE_READ_ONLY_ERROR`, or `PLUGIN_DISMISSED_POST_ERROR`, removes the post entirely.
- Otherwise keeps the post with `props.failed = true`, and creates the thread for it if CRT is enabled.

**2. Automatic retries: none**

`createPost` in `app/client/rest/posts.ts:43` sends `{method: 'post', body: post, noRetry: true}`. `buildRequestOptions` (`app/client/rest/tracking.ts:378`) turns that flag into `retryPolicyConfiguration = {retryLimit: 0}`. So the client makes one attempt. I found no app-level loop that re-invokes `createPost`, though the index can't rule out every caller.

**3. What retrying does**

`retryFailedPost(serverUrl, post)` (`app/actions/remote/post.ts:228`) is called from the failed-post UI (`app/components/post_list/post/body/failed/index.tsx`, `Failed.onPress`). It:

- Clears `failed` and sets a new `create_at`/`update_at` timestamp, so the post shows as pending again. The original `create_at` is not preserved, despite the code comment about it.
- Makes a fresh `client.createPost` call, with the same retry-free policy.
- On success, writes the server's post over the local record and updates the channel's last-post time (unless it is a CRT reply).
- On failure, applies the same handling as the first attempt: removes the post for the three permanent errors, otherwise sets `failed: true` again. It returns `{error}`.

Note that the retry path does not repeat the failure-removal logic exactly as `createPost` does, and it does not call `captureRedactionEpoch` on the error path.