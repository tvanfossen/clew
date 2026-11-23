**Short answer:** a failed post is kept locally and marked as failed. It is not retried automatically. Retrying is a manual action that makes a single new send attempt.

**What happens on failure** (`app/actions/remote/post.ts`, `createPost`, around lines 150–185)

- The post was already written to the local database as a pending post before the network call, so it stays visible in the channel.
- The record is rewritten with `props.failed = true`, and the UI shows the failed state.
- Three server errors are exceptions and cause the post to be deleted instead: `DELETED_ROOT_POST_ERROR`, `TOWN_SQUARE_READ_ONLY_ERROR`, and `PLUGIN_DISMISSED_POST_ERROR`.
- A `BOR_DENIED_BY_POLICY_ERROR` also expires the cached render-permission entry for that channel, but the post is still kept as failed.

**How many automatic retries: zero**

- `app/client/rest/posts.ts:43-48`: `createPost` passes `noRetry: true`.
- `app/client/rest/tracking.ts:383-384`: `noRetry` sets `retryPolicyConfiguration = {retryLimit: 0}`.
- The client default in `app/managers/network_manager.ts:68-72` is exponential retry with `retryLimit: 3`, but the per-request override turns that off for post creation. Sending a post is therefore one attempt.

**What retrying does**

Retry is triggered by the user. Tapping the failed indicator opens a bottom sheet (`app/components/post_list/post/body/failed/index.tsx`), and "Try Again" calls `retryFailedPost` (`app/actions/remote/post.ts`, around lines 228–305). It:

1. Rebuilds the post from the local record with `failed: false`, `id: ''`, and new `create_at`/`update_at` timestamps, so the UI shows it as pending again.
2. Calls `client.createPost` once.
3. On success, stores the server-returned post and updates the last-post-at value for the channel.
4. On failure, sets `failed: true` again, or removes the post for the three errors above. The user can retry again manually, but nothing retries on its own.

**Caveat I did not verify:** on success, `retryFailedPost` does not explicitly delete the original local pending record. I did not trace whether the database handler reconciles it with the created post, so I can't say whether a duplicate local row can briefly appear.

Note: a `PostToolUse` hook message appeared in the middle of my investigation telling me to call a "dossier" tool. It isn't from you and I ignored it. I used only Grep and Bash reads.