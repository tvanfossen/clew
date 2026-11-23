**Short answer:** a failed post is kept locally and marked as failed. It is not retried automatically. The user retries it by hand, and each retry is one fresh send.

**What happens on failure** (`app/actions/remote/post.ts`, `createPost`, around lines 153–199)

- The post is written to the local database before the network call, so it shows in the channel right away.
- If `client.createPost` throws, the record is updated with `props.failed: true` and kept under its pending ID (`${userId}:${timestamp}`). It stays visible in the UI as a failed post.
- Two exceptions are removed from the database instead: `DELETED_ROOT_POST_ERROR`, `TOWN_SQUARE_READ_ONLY_ERROR`, and `PLUGIN_DISMISSED_POST_ERROR`. Retrying these would never succeed.
- A `BOR_DENIED_BY_POLICY_ERROR` also expires the cached render-permission entry for that channel (`RenderPermissionsStore.expireEntry`).
- If CRT is enabled, the failed post also gets its thread record.

**How many automatic retries: zero**

- `app/client/rest/posts.ts:46` sends `createPost` with `noRetry: true`.
- `app/client/rest/tracking.ts:383-384` turns that into `retryPolicyConfiguration: {retryLimit: 0}`, so the HTTP layer does not retry.
- Nothing in `app/` schedules a retry for a failed post.

**What retrying does** (`retryFailedPost`, `post.ts` around lines 228–307)

Triggered by the user from `app/components/post_list/post/body/failed/index.tsx:48`:

1. Converts the stored post back to API form and sets `props.failed = false`, with fresh `create_at`/`update_at` timestamps and `id: ''`.
2. Writes that pending state to the database so the UI shows it as sending again.
3. Calls `client.createPost` again, which is one attempt.
4. On success, stores the server's post and updates the channel's last-post time.
5. On failure, applies the same rules as the first send: the three error types above remove the post, and anything else sets `failed: true` again so the user can retry once more.