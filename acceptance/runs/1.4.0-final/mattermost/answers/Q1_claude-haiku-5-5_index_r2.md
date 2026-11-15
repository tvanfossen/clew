**Short answer:** a failed post is kept locally and marked failed. It is not retried automatically: `createPost` makes exactly one server request with retries disabled. The user retries by tapping "Try Again", which re-sends the same post once.

**1. First send fails (`createPost`, `app/actions/remote/post.ts:74-226`)**

- The post was already written to the local database as an optimistic record before the request, keyed by `pendingPostId`.
- `client.createPost` runs once. The REST call is marked `noRetry: true` (`app/client/rest/posts.ts:43-48`), which sets `retryPolicyConfiguration = {retryLimit: 0}` (`app/client/rest/tracking.ts:383-385`).
- On error, the post is stored with `props.failed = true` and an updated `update_at`, and it stays in the channel with an error icon. With CRT enabled, a thread is also created for it.
- Two exceptions remove the post instead of marking it failed: `DELETED_ROOT_POST_ERROR`, `TOWN_SQUARE_READ_ONLY_ERROR`, and `PLUGIN_DISMISSED_POST_ERROR`.
- A `BOR_DENIED_BY_POLICY_ERROR` also expires the cached render-permissions entry for the channel.

**2. Manual retry (`retryFailedPost`, `app/actions/remote/post.ts:228-307`)**

- The only caller is the "Try Again" item in the failed-post bottom sheet (`app/components/post_list/post/body/failed/index.tsx:46-49`). Nothing calls it automatically.
- It rebuilds the post with `id: ''` and fresh `create_at`/`update_at` timestamps, and sets `failed: false`. The local record is updated first, so the UI shows it as pending again.
- It then calls `client.createPost` once. On success it writes the server-returned post and updates the channel's last-post time. The local record keeps its `pendingPostId`; I did not verify exactly how the receive handler swaps the optimistic record for the server one.
- On failure it applies the same logic as the first attempt: the two error IDs above remove the post, and any other error sets `failed: true` again. The user can tap "Try Again" again.

**Also relevant:** `isPostPendingOrFailed` (`app/utils/post/index.ts:98`) treats a post still pending past `POST_TIME_TO_FAIL` as failed, so a send that never returns is shown as failed without any error being raised.