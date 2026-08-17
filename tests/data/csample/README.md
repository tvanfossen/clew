# demobot firmware

demobot is a sample floor-robot firmware sketch: a cloud-connected appliance
that reports telemetry and responds to remote commands. It exists to
demonstrate documentation enforcement (doxygen-guard) and the layered
documentation database (clew.db) built on top of it.

## Features

The firmware polls battery voltage into a shared data model, publishes
telemetry, and executes commands received from the cloud. The flagship demo
feature is **find-my-robot**: a user taps "ping" in the mobile app, the cloud
forwards the command, and the robot plays an audible locating chime so the
user can find it under the couch.

## Architecture

Subsystems communicate through two decoupling seams: an **event bus**
(function-pointer subscriptions, queued dispatch) and a **generated data
model** — an [ingot](https://github.com/tvanfossen) C99 key-value store
generated from `data/demobot_datamodel.toml` into `gen/ingot/`, with typed
per-key accessors and a change-event callback. Writers and readers never
call each other directly. See `docs/architecture.md` for the full
walkthrough of why the find-my-robot command never directly calls the
sound service.
