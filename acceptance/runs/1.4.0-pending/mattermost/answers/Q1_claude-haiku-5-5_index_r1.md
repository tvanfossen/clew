**Short answer:** a failed send is kept locally and marked failed. It is not retried automatically: `createPost` makes exactly one request. Retrying is a manual "Try Again" action that makes one more single attempt.

**1. What happens on failure**

`createPost` in `app/actions/remote/post.ts:74-226` writes the post to the local database with a pending ID before calling the server. If `client.createPost` throws, the catch block (lines 156-198) branches:

- **Root post deleted, town square read-only, or plugin-dismissed** (`DELETED_ROOT_POST_ERROR`, `TOWN_SQUARE_READ_ONLY_ERROR`, `PLUGIN_DISMISSED_POST_ERROR`): the post is removed with `removePost` (line 181).
- **Any other error:** the post is kept with `props.failed = true` (lines 164-196). It stays visible in the thread and is shown as failed.
- **Burn-on-read denied by policy:** the cached render-permission entry for the channel is expired (line 161).

**2. Automatic retries: none for new posts**

- `app/client/rest/posts.ts:43-47`: `createPost` is sent with `noRetry: true`.
- `app/client/rest/tracking.ts:383-384`: `noRetry` sets `retryPolicyConfiguration = {retryLimit: 0}` for that request.
- The app-wide default in `app/managers/network_manager.ts:68-73` is exponential retry with `retryLimit: 3`, but the per-request override replaces it for posts.

The likely reason is that a POST that times out may already have created the post on the server. Replaying it would duplicate the message. The detox helper `isReplayableBody` in `detox/e2e/support/server_api/client.ts` documents the same concern.

**3. What "retry" does**

The user opens the failed-post bottom sheet and taps "Try Again" (`app/components/post_list/post/body/failed/index.tsx:46-49`), which calls `retryFailedPost` (`app/actions/remote/post.ts:228-307`). That function:

1. Rebuilds the post from its stored API form, sets `props.failed = false`, and resets `create_at`/`update_at` to now. The UI shows it as pending again.
2. Makes a single `client.createPost` call (the same no-retry path).
3. On success, stores the server's post and updates the channel's last-post time (and CRT thread state where relevant).
4. On failure, it either removes the post (the three "post is no longer valid" error IDs) or sets `failed: true` again. It does not loop.

**Caveat:** I read the code but did not run the app or a test. I did not verify that `toApi()` carries `pending_post_id` through the retry, which matters for deduplication.