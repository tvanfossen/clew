# demobot architecture

## Generated data model as the decoupling seam

The data model is not hand-written: `data/demobot_datamodel.toml` is the
source of truth, and the [ingot](https://github.com/tvanfossen) code
generator emits the C99 key-value store under `gen/ingot/` — perfect-hash
key lookup, typed per-key inline accessors
(`DataModel_Set_DEMOBOT_UX_SOUND_EVENT(...)`), a change-event callback, and
a resolved manifest (`dm_full.yaml`) for downstream tools. The generated
output is committed, so building the sample needs no Rust toolchain;
`ingot --model data/demobot_datamodel.toml --output gen/ingot/ --target
linux64` refreshes it when the schema changes.

Subsystems never call across module boundaries directly. A producer writes a
typed key (`DataModel_Set_*`); the store invokes the registered change
callback; interested consumers react from the dispatch handler. This keeps
producers ignorant of consumers — the command handler that sets
`DEMOBOT_UX_SOUND_EVENT` has no idea a sound service exists, and the sound
service does not care whether the trigger came from the cloud, a button, or
a test harness.

The cost of this decoupling is discoverability: no static call graph connects
a key's writers to its readers. The clew.db shared-key layer exists precisely
to restore that link as queryable data.

## Find-my-robot flow

The find-my-robot feature ("ping") travels the whole seam: the cloud command
arrives on the event bus, `handle_cloud_command` recognises the `ping`
payload and delegates to `handle_ping_cmd`, which writes `SOUND_FINDME` into
`DEMOBOT_UX_SOUND_EVENT`. The generated store fires its change callback;
`handle_dm_key_event` sees the key and plays the locating chime. Requirement
REQ-0621 covers the end-to-end behaviour.

## Event paths

Two distinct callback registrations exist, both function-pointer based:

- **Cloud commands** ride the hand-written event bus: handlers are
  registered at init (`event_bus_subscribe_cmd`) and invoked from the main
  loop's dispatch pass.
- **Data-model changes** ride the generated store: `dm_event_dispatch_init`
  passes `handle_dm_key_event` to the generated `DataModel_Initialize`,
  which stores it and invokes it on every successful set.

Because both paths go through pointers, a plain text search for a handler's
name never finds its dispatch site — the clew.db callback layer resolves
these edges, including through the generated code.

## Legacy code

`src/legacy/` contains an ADC calibration routine retained from a previous
hardware revision. Nothing in the current firmware calls it. It is kept in
the tree deliberately: fully documented, requirement-tagged, and dead — the
reachability layer of clew.db is what tells you that.
