**Short answer:** a failed post stays in the channel marked as failed, it is not retried automatically, and "Try Again" resends it as a new server post.

**What happens on failure**

`createPost` (`app/actions/remote/post.ts:74`) first writes the post locally with a pending ID, then calls the server. If the call throws:

- **Most errors:** the post is kept locally with `props.failed = true`, and a CRT thread is created if CRT is enabled. The post shows the failed indicator.
- **Three server errors remove the post instead:** `DELETED_ROOT_POST_ERROR`, `TOWN_SQUARE_READ_ONLY_ERROR`, and `PLUGIN_DISMISSED_POST_ERROR` call `removePost`, so the user never sees a failed post.
- **`BOR_DENIED_BY_POLICY_ERROR`:** the post is still kept as failed, and the cached render-permission entry for the channel is expired.

The error is only logged at debug level (`logDebug`). The function returns `{data: true}` either way, so the caller is not told the send failed.

**How many automatic retries: zero**

`createPost` in the client (`app/client/rest/posts.ts:43`) sends `noRetry: true`. `buildRequestOptions` (`app/client/rest/tracking.ts:378`) turns that into `retryPolicyConfiguration = {retryLimit: 0}`. The send is attempted once. I found no other retry loop in the post-send path.

**What retrying does**

The failed post shows an icon (`app/components/post_list/post/body/failed/index.tsx`). Tapping it opens a bottom sheet with "Try Again" (`post.failed.retry`) and "Delete Message". "Try Again" calls `retryFailedPost` (`app/actions/remote/post.ts:228`), which:

1. Sets `failed: false` on the local post and bumps its `update_at`, so the UI shows it as pending again.
2. Calls `client.createPost` again, sending a new post built from the local record. The timestamps are reset, though `create_at` is set to the retry time rather than 0 as in the original send.
3. On success, stores the server's returned post and updates the channel's last-post time.
4. On failure, sets `failed: true` again, unless it is one of the three removal errors above, in which case the post is deleted.

Retry is manual, one attempt per tap. Nothing re-sends in the background.

**Unresolved from the index:** I did not confirm how the server's returned post replaces the local record keyed by the original pending ID after a successful retry. That reconciliation would need the post handler code, which I did not read.