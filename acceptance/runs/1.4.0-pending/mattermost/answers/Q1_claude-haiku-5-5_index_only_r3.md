**Short answer:** A failed send is kept locally and marked failed. It is not retried automatically: the index shows zero automatic retries. The user retries manually with "Try Again," which makes one more send attempt.

**What happens on the first failure** (`createPost`, `app/actions/remote/post.ts:74-226`)

- The post is written to the local database before the network call, under a `pending_post_id`, so it shows immediately.
- `client.createPost` is called once. `ClientPosts.createPost` passes `noRetry: true` to `doFetch` (`app/client/rest/posts.ts:43-48`), which is what keeps the client layer from retrying.
- On error, the post is stored with `props.failed = true` and shown with an error icon.
- Three server errors are exceptions: `DELETED_ROOT_POST_ERROR`, `TOWN_SQUARE_READ_ONLY_ERROR`, and `PLUGIN_DISMISSED_POST_ERROR`. For these the post is removed rather than kept as failed.
- A `BOR_DENIED_BY_POLICY_ERROR` also expires the cached render-permission entry for that channel.

**How many automatic retries:** zero. Nothing in the index loops or reschedules a failed create. The only retry-like constants in the app are for unrelated things (websocket reconnects, ephemeral wipe, permissions store).

**What the user's retry does** (`retryFailedPost`, `app/actions/remote/post.ts:228-307`)

- The failed-post component (`app/components/post_list/post/body/failed/index.tsx`) opens a bottom sheet with "Try Again" (`post.failed.retry`) and "Delete Message."
- "Try Again" calls `retryFailedPost`, which rebuilds the API post with `failed: false`, new `create_at`/`update_at` timestamps, and `id: ''`. It writes that to the existing local record as the pending state, then calls `client.createPost` once more.
- On success, the server post is upserted, the channel's last-post-at is updated (unless it is a CRT reply), and the local record is replaced.
- On failure, it sets `failed: true` again. The same three error IDs remove the post instead.

**Things to check:**
- `retryFailedPost`'s comment says `create_at` stays the same as the first attempt, but the code sets `create_at: timestamp`. Either the comment or the code is wrong.
- I did not inspect `doFetch` to confirm exactly what `noRetry` disables. The conclusion of no automatic retry rests on the flag plus the absence of any retry loop in the index.