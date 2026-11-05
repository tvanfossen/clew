**Short answer:** the failed post stays in the local database, flagged as failed. The send is never retried automatically, so it is attempted exactly once. A user "Try Again" re-sends the same post content in place.

**What happens on the first failure** (`createPost`, `app/actions/remote/post.ts:74-226`)

1. Before the network call, the post is written locally with a `pending_post_id` and a temporary id, so it shows in the UI immediately.
2. `client.createPost` is called once. It sends `noRetry: true` (`app/client/rest/posts.ts:43-48`), and `buildRequestOptions` maps that to `retryPolicyConfiguration = {retryLimit: 0}` (`app/client/rest/tracking.ts:383-385`). The network layer does not retry it.
3. On error, the code logs the error and then branches:
   - **Root post deleted, Town Square read-only, or plugin-dismissed post** (`DELETED_ROOT_POST_ERROR`, `TOWN_SQUARE_READ_ONLY_ERROR`, `PLUGIN_DISMISSED_POST_ERROR`): the post is removed with `removePost`. It is not kept.
   - **Any other error:** the post is saved with `props.failed = true` and `update_at` set to now. If CRT is enabled, the thread is updated too.
   - **`BOR_DENIED_BY_POLICY_ERROR`:** also expires the cached render-permission entry for the channel.
4. The function returns `{data: true}`, not an error. The caller is not told the send failed.

**What "Try Again" does** (`retryFailedPost`, `app/actions/remote/post.ts:228-307`)

It is wired to the "Try Again" item (`post.failed.retry`) in the failed-post bottom sheet (`app/components/post_list/post/body/failed/index.tsx:46-49`).

- It clears `failed` and bumps `update_at` on the existing local post, so the UI goes back to pending. `create_at` stays the same.
- It rebuilds the API payload from the stored model with `toApi()` and calls `client.createPost` again. Unlike the first attempt, this call does not set `noRetry`, so the network layer's default retry policy applies. I did not verify that default.
- On success, it stores the server's post and updates the last-post time for the channel. For non-CRT-reply posts, it also updates the channel's `last_post_at`.
- On failure, it marks the post failed again. The same three removal cases apply, so a deleted root or read-only Town Square removes the post instead.

**Caveats**

- The number of automatic retries is zero at the app level. Any retry that does happen comes from the network client's default policy during "Try Again", which I didn't check.
- I did not verify how the reducer reconciles the server-created post with the pending local record after a successful retry.
- `retryFailedPost` also returns `{error}` on failure, so its caller can see the failure. `createPost` returns `{data: true}` even when the send failed.