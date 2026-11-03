**Short answer:** a failed post stays in the local database marked as failed, the send is attempted exactly once with no automatic retry, and "Try Again" re-sends the same local post in place.

**1. What happens to the post on failure**

`createPost` in `app/actions/remote/post.ts:74` writes the post locally before calling the server, using a pending ID (`${currentUserId}:${timestamp}`). If `client.createPost` throws, the code takes the failure branch (around lines 150–175):

- For three specific server errors, the post is removed locally with `removePost`: `DELETED_ROOT_POST_ERROR`, `TOWN_SQUARE_READ_ONLY_ERROR` and `PLUGIN_DISMISSED_POST_ERROR`. There is nothing left to retry.
- For any other error, the post is kept with `props.failed = true` and written with `handlePosts`. If CRT is enabled, its thread is also updated.
- A `BOR_DENIED_BY_POLICY_ERROR` also expires the cached render-permission entry for that channel.
- The function returns `{data: true}`, not an error, so the caller never sees the failure.

**2. Automatic retries: none**

The send is attempted once. `ClientPosts.createPost` (`app/client/rest/posts.ts:43`) passes `noRetry: true`, and `buildRequestOptions` in `app/client/rest/tracking.ts:383` turns that into `retryPolicyConfiguration = {retryLimit: 0}`. I did not find any other retry loop in `app/client` or the network manager. The only other retry logic there is the WebSocket reconnect backoff, which is unrelated to posts. I'm inferring that the network library honours `retryLimit: 0`; I did not check the library source.

**3. What "Try Again" does**

The "Try Again" action in `app/components/post_list/post/body/failed/index.tsx:46-48` calls `retryFailedPost(serverUrl, post)` (`app/actions/remote/post.ts:228`). It is user-initiated, so it is the only retry path. It:

1. Rebuilds the API payload from the local model with `post.toApi()`.
2. Sets `failed: false` and a new `update_at`, and writes that to the local record so the UI shows it as pending again.
3. Calls `client.createPost` once more.
4. On success, stores the server's post and updates the channel's last-post time, skipping that update for CRT replies.
5. On failure, either removes the post (for the three terminal errors) or sets `failed: true` again.

Retry keeps the original `create_at` for the server payload, but `retryFailedPost` builds a new object with `create_at` set to the current time. Note that `retryFailedPost` does not explicitly delete the old pending record on success. I did not trace whether `handlePosts` reconciles it away.