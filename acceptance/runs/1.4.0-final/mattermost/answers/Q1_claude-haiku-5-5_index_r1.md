**Short answer:** the post is kept locally and marked failed. The app makes zero automatic retries. The user retries by hand from the failed post's menu.

**What happens on the first failure** (`createPost`, `app/actions/remote/post.ts:74`)

1. Before the network call, the app writes the post to the local DB as a pending record. Its id is `pending_post_id` (`${userId}:${timestamp}`) and it is visible in the channel.
2. `client.createPost` is called once. `ClientPosts.createPost` passes `noRetry: true` (`app/client/rest/posts.ts:46`), and `tracking.ts:383-384` turns that into `retryPolicyConfiguration = {retryLimit: 0}`. So the request is not retried at the HTTP layer either.
3. If the call throws, the post record is rewritten with `props.failed = true`. Its `update_at` is set to now.
4. Three server errors are exceptions and cause the post to be deleted instead: `DELETED_ROOT_POST_ERROR`, `TOWN_SQUARE_READ_ONLY_ERROR`, and `PLUGIN_DISMISSED_POST_ERROR` (`post.ts` around line 130). `BOR_DENIED_BY_POLICY_ERROR` does not delete the post. It expires the cached render-permission entry for the channel.
5. Any other error, including network errors, leaves the post in place as failed. CRT thread models are updated when CRT is enabled.

**What the user sees and does**

Tapping a failed post opens a bottom sheet (`app/components/post_list/post/body/failed/index.tsx:37-68`) with two actions:
- **Try Again** (`post.failed.retry`) calls `retryFailedPost`.
- **Delete Message** (`post.failed.delete`) calls `removePost`.

**What "Try Again" does** (`retryFailedPost`, `post.ts:228-307`)

1. Converts the stored post back to an API post and sets `props.failed = false`. It sets `create_at` and `update_at` on the request body to the current time.
2. Writes the pending state locally first: it updates `props` and `updateAt` on the existing record, so the post goes back to the sending state immediately.
3. Calls `client.createPost` once more. This is a single attempt, with no retry loop.
4. On success, the server response is written with `handlePosts`, and the channel's last-post time is updated when the reply is not a CRT reply.
5. On failure, the same logic as above applies. The three removal errors delete the post. Any other error sets `props.failed = true` again, so the user can retry again.

**Caveats**
- The comment in `retryFailedPost` says the create timestamp stays the same as the original attempt. The code sets `create_at` to a new timestamp on the request body. The local record keeps its original `create_at`, since only `props` and `updateAt` are changed.
- I did not confirm how the local pending record is cleaned up after a successful retry, which is the step where the server-id record replaces the pending one. I only read the `handlePosts` call.