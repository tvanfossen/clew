**Short answer:** a failed post stays in the local database, marked as failed, with no automatic retries. Only a manual "Try Again" retries it, and that re-sends it as a fresh create request.

**1. What happens on failure**

`createPost` (`app/actions/remote/post.ts:74`) saves the post locally first, under a pending ID (`pending_post_id`), so it shows in the UI. If `client.createPost` throws, the code takes one of two paths:

- **Deleted root post, town square read-only, or plugin-dismissed post** (`ServerErrors.DELETED_ROOT_POST_ERROR`, `TOWN_SQUARE_READ_ONLY_ERROR`, `PLUGIN_DISMISSED_POST_ERROR`): the post is removed with `removePost`. It is not kept as a failed post.
- **Any other error**: the post is rewritten with `props.failed = true` and saved. For a CRT reply, a thread is also created from it. A `BOR_DENIED_BY_POLICY_ERROR` additionally expires the cached render-permissions entry.

**2. Automatic retries: zero**

`ClientPosts.createPost` (`app/client/rest/posts.ts:46`) passes `noRetry: true`. In `buildRequestOptions` (`app/client/rest/tracking.ts:383`) that sets `retryPolicyConfiguration = {retryLimit: 0}`, so the network layer does not retry the POST. The only caller of `retryFailedPost` is the failed-post bottom sheet's "Try Again" action (`app/components/post_list/post/body/failed/index.tsx:48`). Nothing retries on reconnect or on a timer.

**3. What "retry" does**

Retry is a user action that calls `retryFailedPost` (`app/actions/remote/post.ts:228`):

1. It builds a new API post from the stored one, with `failed: false`, `create_at` and `update_at` set to now, and `id` blanked.
2. It updates the local record to show the pending state, keeping the original `create_at` and updating `update_at`.
3. It calls `client.createPost` again. This is a fresh POST, which the server treats as a new post. The only link back to the original is `pending_post_id`, and the code does not check whether the server already has the post.
4. On success, it writes the server-created post and updates the channel's last-post time (unless it is a CRT reply).
5. On failure, the same branch rules apply again: server-error cases remove the post, and anything else marks it failed again.