**Short answer:** the post is kept locally and marked failed. It is not retried automatically at all. "Try Again" is a manual retry that sends a fresh create request.

**1. What happens to the post on failure**

In `createPost` (`app/actions/remote/post.ts:74-226`), the post is written to the local database before the network call, with a temporary `pending_post_id`. If `client.createPost` throws, the code takes one of two paths:

- **Post is kept (the usual case):** the record is rewritten with `props.failed = true` and `update_at = now`, and it stays visible in the channel. The UI shows an error icon (`post.failed.button`, `app/components/post_list/post/body/failed/index.tsx`).
- **Post is removed:** if the server error is `DELETED_ROOT_POST_ERROR`, `TOWN_SQUARE_READ_ONLY_ERROR`, or `PLUGIN_DISMISSED_POST_ERROR`, the post is deleted locally instead, since retrying could never succeed.

Also, `app/utils/post/index.ts:98` treats a pending post as failed once it has been pending longer than `POST_TIME_TO_FAIL` (10 seconds, `app/constants/post.ts:57`), even without the `failed` flag.

**2. Automatic retries: none at the app level**

The client's default retry policy is exponential with `retryLimit: 3` (`app/managers/network_manager.ts:68-73`). But `createPost` in `app/client/rest/posts.ts:43-47` passes `noRetry: true`, which `app/client/rest/tracking.ts:383-385` turns into `retryPolicyConfiguration: {retryLimit: 0}`. So a failed post send is attempted exactly once. The Android native layer sets its own retry defaults (`android/.../Network.java:58-63`), but that only applies to the client's default policy, and the `noRetry` override on this request still applies.

**3. What "Try Again" does**

`retryFailedPost` (`app/actions/remote/post.ts:228-301`) runs when the user picks "Try Again" in the bottom sheet (`post/body/failed/index.tsx:46-49`):

1. It clears `props.failed` and sets `update_at` to now, so the post shows as pending again.
2. It sends a new `client.createPost` request built from the post's API form, with a new `create_at`/`update_at` and an empty `id`, so the server assigns a new post ID.
3. On success, the response replaces the local record. On a server error it re-marks the post as failed, or removes it for the three non-retryable error IDs above.

Caveat: I did not confirm whether `toApi()` carries the original `pending_post_id` through to the server or how the local record is swapped on success. Check `PostModel.toApi` and the `handlePosts` pending-ID matching if that matters for your change.