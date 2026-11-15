**Short answer:** A failed post stays in the local database, marked as failed, and is not removed unless the server rejects it for a specific reason. There are zero automatic retries. Retrying is manual: the user taps "Try Again", which re-sends the same local post.

**What happens on failure** (`app/actions/remote/post.ts:74`, `createPost`)

1. The post is written to the database optimistically before the network call, keyed by `pending_post_id`.
2. If `client.createPost` throws, the code builds an error copy of the post with `props.failed = true` and saves it, along with its thread if CRT is enabled.
3. Three server errors are the exception. If the server returns `DELETED_ROOT_POST_ERROR`, `TOWN_SQUARE_READ_ONLY_ERROR` or `PLUGIN_DISMISSED_POST_ERROR`, the post is deleted locally instead of kept as failed.
4. `BOR_DENIED_BY_POLICY_ERROR` also expires the cached render-permission entry for that channel. The post is still kept as failed.

**How many automatic retries: none**

- `ClientPosts.createPost` (`app/client/rest/posts.ts:43`) passes `noRetry: true`.
- `buildRequestOptions` (`app/client/rest/tracking.ts:383`) turns that into `retryPolicyConfiguration: {retryLimit: 0}`.
- The client default in `app/managers/network_manager.ts:68` is exponential retry with `retryLimit: 3`, but the post path overrides it. A failed send is not retried by the network layer.

**What retrying does** (`app/actions/remote/post.ts:228`, `retryFailedPost`)

- The user taps the failed icon (`app/components/post_list/post/body/failed/index.tsx`), which opens a sheet with "Try Again" and "Delete Message". "Try Again" calls `retryFailedPost`.
- It does not create a new post. It takes the existing local record, sets `failed: false`, and updates its `update_at` timestamp. `create_at` stays as it was.
- It then calls `client.createPost` again with the same content. On success it writes the server's post to the database and updates the channel's last-post time, unless the post is a CRT reply.
- On failure it sets `failed: true` again, or deletes the post if the error is one of the three removal errors above. It does not retry on its own.

**Caveat:** I read the code but did not run the app or any tests.