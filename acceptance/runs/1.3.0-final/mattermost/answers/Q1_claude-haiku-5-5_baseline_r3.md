**Short answer:** the post is kept locally and marked failed. It is not retried automatically: the send happens once, with HTTP retries disabled. Retrying is a manual action, and each tap sends one more attempt.

**1. What happens to the post on failure**

`createPost` in `app/actions/remote/post.ts:74` writes the post to the local database before calling the server, under a `pending_post_id`. If `client.createPost` throws (lines 154–199), it:

- Logs the error with `logDebug`.
- Rebuilds the post with `props.failed: true` and an updated `update_at`.
- Saves it to the database, and creates a thread too if CRT is enabled.

The one exception is three server errors: `DELETED_ROOT_POST_ERROR`, `TOWN_SQUARE_READ_ONLY_ERROR` and `PLUGIN_DISMISSED_POST_ERROR`. For those, `removePost` deletes the local post (lines 176–181). Any other failure leaves the post in place.

The UI also treats a post as failed when `props.failed` is set, or when it has stayed pending longer than `POST_TIME_TO_FAIL`, which is 10 seconds (`app/utils/post/index.ts:97`, `app/constants/post.ts:57`).

**2. How many automatic retries: zero**

- `createPost` in `app/client/rest/posts.ts:43` passes `noRetry: true`.
- `app/client/rest/tracking.ts:383–384` turns that into `retryPolicyConfiguration: {retryLimit: 0}`.
- `createPost` in `app/actions/remote/post.ts` has no loop around the call.

So a failed send is attempted once and then marked failed.

**3. What retrying does**

The retry button is in `app/components/post_list/post/body/failed/index.tsx`. Tapping the failed icon opens a sheet with "Try Again" (`post.failed.retry`) and "Delete Message". "Try Again" calls `retryFailedPost` (`app/actions/remote/post.ts:228`), which:

1. Converts the stored post back to an API object and clears `props.failed`. It also sets a new `update_at` and `create_at`, so the optimistic UI shows the post as pending again. Its `create_at` is only sent in the request; the local `create_at` is unchanged.
2. Saves that pending state, then calls `client.createPost` once more.
3. On success, saves the server's post and updates the channel's last-post time.
4. On failure, either removes the post (for the same three errors) or sets `props.failed` again so the user can retry.

Each retry is a single manual attempt. The failure handling is the same as the first send.

One inconsistency: the comment at lines 260–261 says the create timestamp stays the same as the first attempt. The code does send a new `create_at`, though the local record keeps the original, so the comment does not match the code.