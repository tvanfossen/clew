**Short answer:** the post is kept locally and marked failed. It is not retried automatically at all: the send is attempted once. Retrying happens only when the user chooses "Try Again."

**What happens on failure**

1. `createPost` (`app/actions/remote/post.ts:74`) first writes an optimistic local post with a `pending_post_id` and `id: ''`, so it shows in the UI before the server responds.
2. It makes one `client.createPost(...)` call. If that throws, it logs the error and builds an error copy of the post with `props.failed: true`.
3. Two server errors are exceptions: `DELETED_ROOT_POST_ERROR`, `TOWN_SQUARE_READ_ONLY_ERROR` and `PLUGIN_DISMISSED_POST_ERROR` cause `removePost`, which deletes the post. `BOR_DENIED_BY_POLICY_ERROR` also expires the cached render-permission entry for the channel.
4. Every other failure saves the post with `failed: true`. If CRT is enabled, the thread is created as well.

**Automatic retries: zero**

- `ClientPosts.createPost` (`app/client/rest/posts.ts:43`) passes `noRetry: true`.
- `doFetchWithTracking` (`app/client/rest/tracking.ts:395`) makes a single request. Its only `try` wraps that one call, and it rethrows as a `ClientError`. I found no retry loop in it. I did not open `buildRequestOptions` to see how it uses `noRetry`, but the function body has no loop.

**Manual retry (`retryFailedPost`, `app/actions/remote/post.ts:228`)**

The failed post's "Try Again" action (`app/components/post_list/post/body/failed/index.tsx:37`, testID `post.failed.retry`) calls this function. It:

1. Clears `failed` on the post's props, resets `create_at`/`update_at` to now, and saves that state so the UI shows it as pending again.
2. Captures the redaction epoch and calls `client.createPost` again with `id: ''`.
3. On success, writes the server's post, updates the channel's last-post time (unless it is a CRT reply), and saves the result.
4. On failure, applies the same logic as the first attempt: the three special server errors remove the post, and anything else sets `failed: true` again.

The "Delete Message" option calls `removePost` directly.