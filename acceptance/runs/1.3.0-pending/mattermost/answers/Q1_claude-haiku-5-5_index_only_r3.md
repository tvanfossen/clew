**Short answer:** a failed new post is kept locally, marked as failed, and never retried automatically. Retrying happens only when the user taps "Try Again."

**What happens on failure**

1. `createPost` in `app/actions/remote/post.ts` (lines 74–226) saves the post locally first, as a pending record with a `pending_post_id`, so it shows in the UI right away.
2. It then calls `client.createPost` once. If that throws, the catch block logs the error and checks the server error ID:
   - **Root post deleted, town square read-only, or plugin-dismissed post:** the post is removed with `removePost`.
   - **Any other error:** the local post is rewritten with `props.failed = true`, and kept. If CRT is enabled, its thread record is created too.
3. For the burn-on-read policy error, the cached render-permission entry for the channel is also expired.

**Automatic retries: none**

- The REST call `ClientPosts.createPost` in `app/client/rest/posts.ts` (lines 43–48) passes `noRetry: true` to `doFetch`. So the client's own retry layer is explicitly disabled for this call.
- `createPost` itself has no loop or timer. Nothing in the indexed code schedules a second attempt.

**What retrying does**

- The user taps the failed post, which opens a bottom sheet (`app/components/post_list/post/body/failed/index.tsx`). "Try Again" (`post.failed.retry`) calls `retryFailedPost(serverUrl, post)`. "Delete Message" removes it.
- `retryFailedPost` (`app/actions/remote/post.ts`, lines 228–307):
  - Rebuilds the API payload from the stored post and clears `failed`.
  - Resets the timestamps (`create_at` and `update_at` are set to now) and writes the pending state back to the DB.
  - Makes one `client.createPost` call.
  - On success, stores the server post and updates the channel's last-post time.
  - On error, it sets `failed` back to true, or removes the post for the same three server error IDs as above.
- Each tap is one attempt. There is no retry count to tune.

**Caveat:** the index shows that `noRetry` is passed but not where it is read. The retry layer is presumably in the `@mattermost/react-native-network-client` dependency, which the index does not cover. I did not confirm that layer's behaviour.