**Short answer:** a failed new-post send is kept locally and marked failed. It is not retried automatically: there is one network attempt, and the user has to retry by hand. Retrying re-sends the same post, not a new one.

**What happens on failure**

- `createPost` in `app/actions/remote/post.ts:74` writes the post to the local database first, with a `pending_post_id`, before calling the server. That is what the user sees as a pending post.
- It then calls `client.createPost` once. `ClientPosts.createPost` in `app/client/rest/posts.ts:43` passes `noRetry: true`, which turns off the client's transport retry for this request.
- On error, the catch block (`post.ts`, around lines 125–160) logs the error and then branches on the server error ID:
  - `DELETED_ROOT_POST_ERROR`, `TOWN_SQUARE_READ_ONLY_ERROR` or `PLUGIN_DISMISSED_POST_ERROR`: the local post is removed with `removePost`.
  - Any other error: the post is stored with `props.failed = true` and its `id` set to the pending ID. If CRT is enabled, its thread record is created too. The post stays in the database as a failed post.
  - A `BOR_DENIED_BY_POLICY_ERROR` also expires the render-permissions entry for the channel.
- The function returns `{data: true}` in both cases, so the caller does not treat a failed send as an error.

**How many automatic retries:** zero. I found no retry loop in the send path. The only retry-related code in the send path is `noRetry: true`. The other retry constants in the index (websocket, calls, performance metrics, ephemeral wipe) are unrelated to posts.

**What retrying does:** `retryFailedPost` in `post.ts:228` runs when the user taps the failed post (its caller is `app/components/post_list/post/body/failed/index.tsx`). It:

1. Clears `failed` in the props and sets a new `create_at`/`update_at` timestamp. `create_at` is set to the retry time, not the original time. The local record is updated so the UI shows it as pending again.
2. Calls `client.createPost` with the same content, again with no automatic retry.
3. On success, stores the server's post and updates the channel's last-post time (unless it is a CRT reply).
4. On failure, it either removes the post (for the same three error IDs) or sets `failed: true` again.

**Caveat:** the index only shows the code paths I could query. I did not confirm the exact UI wiring beyond the caller listed above.