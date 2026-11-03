**Short answer:** a failed new post stays on the device, marked as failed, and is never retried automatically. The send is attempted once. "Try Again" in the user's menu re-sends it, and the post is updated in place.

**What happens on failure**

1. `createPost` in `app/actions/remote/post.ts` (line 74) writes the post to the local DB first, under a `pending_post_id`, so it shows immediately.
2. It calls `client.createPost`. If that throws, the catch block (lines 156–198) runs.
3. Most errors take the normal path: the post is kept with `props.failed = true` (lines 164–196). The exceptions are `DELETED_ROOT_POST_ERROR`, `TOWN_SQUARE_READ_ONLY_ERROR`, and `PLUGIN_DISMISSED_POST_ERROR`, which delete the local post instead (line 181). A `BOR_DENIED_BY_POLICY_ERROR` also expires the cached render permission entry (line 161).
4. The UI treats a post as failed if `props.failed` is set, or if it is still pending more than `POST_TIME_TO_FAIL` (10 seconds, `app/constants/post.ts:57`) after its last update (`app/utils/post/index.ts:98`).

**How many automatic retries: zero**

`app/client/rest/posts.ts:46` sends the create request with `noRetry: true`. `app/client/rest/tracking.ts:383–384` turns that into `retryPolicyConfiguration = {retryLimit: 0}`, which disables the network layer's retry policy for this request. Nothing else in `app/` re-queues failed posts, so a failed post waits for the user.

**What "Try Again" does**

The failed-post icon (`app/components/post_list/post/body/failed/index.tsx`) opens a bottom sheet with "Try Again" and "Delete Message". "Try Again" calls `retryFailedPost` (`app/actions/remote/post.ts:228`), which:

- Clears `props.failed`, refreshes `updateAt`, and keeps the original `createAt`, so the UI shows the post as pending again.
- Calls `client.createPost` once more, with the same single-attempt setting.
- On success, writes the server's post over the local record and updates the channel's last-post time (and thread data if CRT is on).
- On failure, it either deletes the post (same three error codes) or sets `failed` again. It returns `{error}`, so the user can retry as often as they like, but each retry is a single attempt.

The post's `pending_post_id` is kept across retries, so the local record is updated in place rather than duplicated.