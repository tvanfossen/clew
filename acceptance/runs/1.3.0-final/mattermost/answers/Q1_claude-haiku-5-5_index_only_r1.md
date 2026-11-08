**Short answer:** the failed post is kept locally and marked as failed. It is not retried automatically: the send is made with retries disabled. The user retries by tapping the failed-post control, which calls `retryFailedPost`.

**1. What happens to the post on failure**

`createPost` (`app/actions/remote/post.ts:74`) first writes the post to the local database with a pending ID, so it shows in the UI immediately. If the server call throws, it takes one of two paths:

- **Normal failure:** the post is saved with `props.failed = true` and kept in the channel. If CRT is enabled, its thread record is also created.
- **Three specific server errors** (`DELETED_ROOT_POST_ERROR`, `TOWN_SQUARE_READ_ONLY_ERROR`, `PLUGIN_DISMISSED_POST_ERROR`): the post is removed instead of kept as failed.
- **Burn-on-read policy refusal** (`BOR_DENIED_BY_POLICY_ERROR`): the post is kept as failed, and the cached render-permission decision for that channel is expired.

**2. Automatic retries: zero**

- `ClientPosts.createPost` (`app/client/rest/posts.ts:43`) sends the request with `noRetry: true`.
- `buildRequestOptions` (`app/client/rest/tracking.ts:378`) turns that into `retryPolicyConfiguration = {retryLimit: 0}`.
- `doFetchWithTracking` (`tracking.ts:395`) has no retry loop of its own.

The index shows no other retry path for post creation. Whether the native network client applies any retry beyond what `retryLimit: 0` sets is outside what the index can see.

**3. What retrying does (`retryFailedPost`, `app/actions/remote/post.ts:228`)**

Triggered by the `onPress` in `app/components/post_list/post/body/failed/index.tsx:48`:

1. Builds a new API post from the stored record, with `props.failed = false`, `id: ''`, and fresh `create_at`/`update_at`/`delete_at` values.
2. Updates the local record: it clears `failed` and bumps `updateAt`. The local `create_at` is not changed.
3. Sends `client.createPost` again, with the same redaction-epoch capture as the first attempt.
4. On success, stores the server-returned post, updates the channel's last-post time (unless it is a CRT reply), and returns `{}`.
5. On failure, it logs, then either removes the post (for the same three server errors) or sets `failed = true` again. It returns `{error}`. The user can retry again.

**Caveat:** `createPost` has an early return: if a non-failed post with the same pending ID already exists, it does nothing. A failed post passes that check, which is why it can be re-sent.