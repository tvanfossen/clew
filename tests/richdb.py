# SPDX-License-Identifier: MIT
"""Build the synthetic `rich_db` fixture: doxygen's tables by hand, ours for real.

## What is hand-made, and why only that

Exactly four things cannot be produced without running doxygen: the `path` rows,
the `memberdef` rows, the inline `xrefs` that Layer 1 reads, and doxygen's own
schema (loaded verbatim from
`tests/data/doxygen_schema.sql`). Everything else in a clew.db is derived by
clew's own stages from the SOURCE TREE — and the source tree is real
(`tests/data/csample/`), so those stages are RUN, not simulated:

    ingest_supplementary_docs   import_kconfig_gates   recover_ast_symbols
    ingest_file_docs            build_call_edges       import_ast_call_edges
    import_callback_registration_edges                 extract_locks
    extract_threads             import_shared_key_edges_inferred
    import_shared_key_edges_declared                   annotate_thread_boundaries
    ingest_requirements_yaml    import_req_edges       import_req_test_edges
    mark_reachability           write_build_signature

That is eighteen real pipeline stages still exercised by the DEFAULT suite, on
every run, with no doxygen binary. It is also what makes the fixture hard to rot:
a CHECK that tightens, a column that is added, an extractor whose output shape
changes — the fixture takes the change, because the fixture IS the extractor's
output for those layers.

## Naming

The identifiers are the demobot ones — `sensor_poll`, `DEMOBOT_POWER_BATTERY_MV`,
`REQ-0621` — and the memberdef ROWIDS are the ones a real `sample/` build
produced. Both are deliberate: see the rationale in `tests/conftest.py`. The
rowids in particular carry the decl/def duality the suite tests (`sensor_poll` is
76 AND 158, one definition row and one header-declaration row), so keeping the
real numbers keeps the real shape.

@brief Declarative index tables + the rich_db builder.
@version 3
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"
## The real C source tree the index describes. Every `path` row points at a file
## that EXISTS here, so `source()` returns verbatim text and the AST stages have
## something to parse.
CSAMPLE = DATA / "csample"
## Doxygen's own schema, captured from a real build. Never hand-edited. Lives under
## the package (clew/data/) rather than tests/data/ so clew/rustdoc.py — which has
## to synthesize the same tables from rustdoc JSON for a language doxygen cannot
## parse — can load the identical schema without a second copy to drift from this
## one.
DOXYGEN_SCHEMA = Path(__file__).resolve().parent.parent / "clew" / "data" / "doxygen_schema.sql"

## doxygen's `path.type` discriminator.
_TYPE_FILE = 1
_TYPE_DIR = 2


# ─── path rows ───────────────────────────────────────────────────────────────

## Repo-relative source files, keyed by the rowid a real `sample/` build gave
## them. Order is irrelevant (rowid is explicit); the numbers are preserved so a
## fixture row and a measured row are the same row.
FILE_PATHS: dict[int, str] = {
    1: "gen/ingot/dm_key.h",
    2: "gen/ingot/dm.h",
    3: "src/event_bus/event_bus.h",
    4: "gen/ingot/dm.c",
    7: "gen/ingot/integer_storage.h",
    12: "gen/ingot/dm_helpers.h",
    14: "src/dispatch/dm_event_dispatch.c",
    15: "src/sensor/sensor_driver.c",
    16: "src/telemetry/telemetry.c",
    18: "gen/ingot/integer_storage.c",
    23: "src/command/command_handler.c",
    24: "src/command/command_handler.h",
    25: "src/telemetry/telemetry.h",
    26: "src/main.c",
    27: "src/dispatch/dm_event_dispatch.h",
    28: "src/sound/sound_service.h",
    29: "src/event_bus/event_bus.c",
    30: "src/legacy/legacy_calibration.c",
    31: "src/sensor/sensor_driver.h",
    32: "src/sound/sound_service.c",
    33: "test/test_sound.c",
}

## System headers doxygen records but never found on disk (`local=0, found=0`).
## Present because `list_files` has to distinguish a repo file from an include
## doxygen merely mentioned, and a fixture with only repo files cannot show that.
SYSTEM_PATHS: dict[int, str] = {
    5: "string.h",
    8: "pthread.h",
    9: "stddef.h",
    10: "stdint.h",
    11: "stdbool.h",
    21: "stdio.h",
}

## Doxygen's SYNTHETIC path row: everything harvested out of system headers is
## registered against a single bracketed marker. `list_files` must exclude it, and
## without a row like this that assertion passes vacuously — demobot is plain C
## and never produced one, so the exclusion was never actually exercised.
SYNTHETIC_PATHS: dict[int, str] = {45: "[STL]"}

## Directory rows (`type=2`). `list_files` filters on `type`, so a fixture with no
## directory rows cannot show that either.
DIR_PATHS: dict[int, str] = {
    34: "src/command/",
    35: "src/dispatch/",
    36: "src/event_bus/",
    37: "gen/",
    38: "gen/ingot/",
    39: "src/legacy/",
    40: "src/sensor/",
    41: "src/sound/",
    42: "src/",
    43: "src/telemetry/",
    44: "test/",
}

_PATH_ROWID = {name: rowid for rowid, name in FILE_PATHS.items()}


# ─── memberdef rows ──────────────────────────────────────────────────────────


## @brief One `memberdef` row, in the terms a C author would describe it.
## @version 2
@dataclass(frozen=True)
class Row:
    """`body` is the repo-relative file the BODY lives in, which is what makes a
    row a declaration or a definition: doxygen sets `bodyfile_id == file_id` on a
    definition and leaves them different on a documented header declaration. The
    whole decl/def-duality half of the suite rides on that one difference, so it is
    modelled explicitly rather than derived from a boolean.

    @brief A declarative memberdef row.
    @version 2
    """

    rowid: int
    name: str
    ret: str
    args: str
    file: str
    body: str
    start: int
    end: int
    line: int
    brief: str = ""
    req: str = ""
    kind: str = "function"
    version: str = "1.0"
    ## The doxygen `initializer` column: for a `kind='macro definition'` row this is
    ## the EXPANSION, and gh#373 made it reachable through `search` and `dossier`. It
    ## was left empty here while the macro rows existed only to give the
    ## `kind='function'` filter something to reject, and an empty expansion is exactly
    ## the state in which a macro corpus can be tested and prove nothing.
    expansion: str = ""

    ## @brief The doxygen `definition` column: return type plus qualified name.
    ## @return The signature text a `definition` column carries.
    ## @version 1
    @property
    def definition(self) -> str:
        """@brief Assemble the doxygen `definition` text.

        @return "<return type> <name>".
        @version 1
        """
        return f"{self.ret} {self.name}"

    ## @brief Whether doxygen would set the `static` flag on this row.
    ## @return 1 when the return type is `static`-qualified, else 0.
    ## @version 1
    @property
    def static(self) -> int:
        """@brief Read the static flag off the declared return type.

        @return 1 or 0.
        @version 1
        """
        return int(self.ret.startswith("static"))


_SENSOR = "src/sensor/sensor_driver.c"
_SENSOR_H = "src/sensor/sensor_driver.h"
_TELEM = "src/telemetry/telemetry.c"
_TELEM_H = "src/telemetry/telemetry.h"
_BUS = "src/event_bus/event_bus.c"
_BUS_H = "src/event_bus/event_bus.h"
_CMD = "src/command/command_handler.c"
_CMD_H = "src/command/command_handler.h"
_DISPATCH = "src/dispatch/dm_event_dispatch.c"
_DISPATCH_H = "src/dispatch/dm_event_dispatch.h"
_SOUND = "src/sound/sound_service.c"
_SOUND_H = "src/sound/sound_service.h"
_MAIN = "src/main.c"
_TEST = "test/test_sound.c"
_LEGACY = "src/legacy/legacy_calibration.c"
_DM_C = "gen/ingot/dm.c"
_DM_H = "gen/ingot/dm.h"
_HELPERS = "gen/ingot/dm_helpers.h"
_STORE_C = "gen/ingot/integer_storage.c"
_STORE_H = "gen/ingot/integer_storage.h"
_KEY_H = "gen/ingot/dm_key.h"

## Every function row. Body extents are the ACTUAL line ranges in
## `tests/data/csample/`, so `source()` reads the real text and the AST stages
## attribute their call sites to the right enclosing function.
FUNCTIONS: tuple[Row, ...] = (
    # ── src/main.c ──
    Row(
        33,
        "app_run",
        "static void",
        "(void)",
        _MAIN,
        _MAIN,
        16,
        30,
        16,
        "Run a bounded main loop: poll, dispatch, report.",
        "REQ-0200",
    ),
    Row(
        119,
        "main",
        "int",
        "(void)",
        _MAIN,
        _MAIN,
        38,
        47,
        38,
        "Initialise every subsystem, then enter the main loop.",
        "REQ-0200",
    ),
    # ── src/event_bus/ — every one carries a header DECLARATION row too ──
    Row(
        129,
        "event_bus_init",
        "void",
        "(void)",
        _BUS,
        _BUS,
        19,
        25,
        19,
        "Reset the event queue and clear all handler subscriptions.",
        "REQ-0200",
    ),
    Row(
        138,
        "event_bus_init",
        "void",
        "(void)",
        _BUS_H,
        _BUS,
        19,
        25,
        19,
        "Reset the event queue and clear all handler subscriptions.",
        "REQ-0200",
    ),
    Row(
        118,
        "event_bus_subscribe_cmd",
        "void",
        "(event_handler_t handler)",
        _BUS,
        _BUS,
        33,
        36,
        33,
        "Subscribe a handler to cloud command events.",
        "REQ-0200",
    ),
    Row(
        139,
        "event_bus_subscribe_cmd",
        "void",
        "(event_handler_t handler)",
        _BUS_H,
        _BUS,
        33,
        36,
        20,
        "Subscribe a handler to cloud command events.",
        "REQ-0200",
    ),
    Row(
        130,
        "event_bus_publish",
        "void",
        "(const event_t *evt)",
        _BUS,
        _BUS,
        44,
        52,
        44,
        "Enqueue an event for delivery on the next dispatch pass.",
        "REQ-0200",
    ),
    Row(
        140,
        "event_bus_publish",
        "void",
        "(const event_t *evt)",
        _BUS_H,
        _BUS,
        44,
        52,
        21,
        "Enqueue an event for delivery on the next dispatch pass.",
        "REQ-0200",
    ),
    Row(
        34,
        "event_bus_dispatch",
        "int",
        "(void)",
        _BUS,
        _BUS,
        60,
        78,
        60,
        "Drain the queue, delivering each event to its subscribed handler.",
        "REQ-0200",
    ),
    Row(
        141,
        "event_bus_dispatch",
        "int",
        "(void)",
        _BUS_H,
        _BUS,
        60,
        78,
        22,
        "Drain the queue, delivering each event to its subscribed handler.",
        "REQ-0200",
    ),
    # ── src/command/ ──
    Row(
        117,
        "command_handler_init",
        "void",
        "(void)",
        _CMD,
        _CMD,
        18,
        21,
        18,
        "Subscribe the cloud command handler to the event bus.",
        "REQ-0300",
    ),
    Row(
        121,
        "command_handler_init",
        "void",
        "(void)",
        _CMD_H,
        _CMD,
        18,
        21,
        4,
        "Subscribe the cloud command handler to the event bus.",
        "REQ-0300",
    ),
    # static, so no header row: the fnptr layer is the ONLY thing that reaches it.
    Row(
        37,
        "handle_cloud_command",
        "static void",
        "(const event_t *evt)",
        _CMD,
        _CMD,
        30,
        40,
        30,
        "Route a cloud command payload to its feature handler.",
        "REQ-0300",
    ),
    # ── src/dispatch/ ──
    Row(
        78,
        "handle_dm_key_event",
        "static void",
        "(uint32_t key_id)",
        _DISPATCH,
        _DISPATCH,
        16,
        27,
        16,
        "React to data-model key changes reported by the generated store.",
        "REQ-0500",
    ),
    Row(
        45,
        "dm_event_dispatch_init",
        "void",
        "(void)",
        _DISPATCH,
        _DISPATCH,
        34,
        37,
        34,
        "Initialise the generated data model with our change handler.",
        "REQ-0500",
    ),
    Row(
        125,
        "dm_event_dispatch_init",
        "void",
        "(void)",
        _DISPATCH_H,
        _DISPATCH,
        34,
        37,
        4,
        "Initialise the generated data model with our change handler.",
        "REQ-0500",
    ),
    # ── src/sensor/ ──
    Row(
        155,
        "hw_read_battery_adc",
        "static int16_t",
        "(void)",
        _SENSOR,
        _SENSOR,
        17,
        22,
        17,
        "Read the battery ADC channel (simulated hardware).",
    ),
    Row(
        151,
        "sensor_init",
        "void",
        "(void)",
        _SENSOR,
        _SENSOR,
        29,
        32,
        29,
        "Prime the sensor driver's sampling state.",
        "REQ-0100",
    ),
    Row(
        157,
        "sensor_init",
        "void",
        "(void)",
        _SENSOR_H,
        _SENSOR,
        29,
        32,
        4,
        "Prime the sensor driver's sampling state.",
        "REQ-0100",
    ),
    Row(
        76,
        "sensor_poll",
        "void",
        "(void)",
        _SENSOR,
        _SENSOR,
        39,
        42,
        39,
        "Sample battery voltage and publish it into the data model.",
        "REQ-0100",
    ),
    Row(
        158,
        "sensor_poll",
        "void",
        "(void)",
        _SENSOR_H,
        _SENSOR,
        39,
        42,
        5,
        "Sample battery voltage and publish it into the data model.",
        "REQ-0100",
    ),
    # ── src/telemetry/ ──
    Row(
        152,
        "telemetry_init",
        "void",
        "(void)",
        _TELEM,
        _TELEM,
        16,
        19,
        16,
        "Reset telemetry counters.",
        "REQ-0400",
    ),
    Row(
        168,
        "telemetry_init",
        "void",
        "(void)",
        _TELEM_H,
        _TELEM,
        16,
        19,
        4,
        "Reset telemetry counters.",
        "REQ-0400",
    ),
    Row(
        75,
        "telemetry_report",
        "void",
        "(void)",
        _TELEM,
        _TELEM,
        26,
        30,
        26,
        "Format current data-model values for upstream publication.",
        "REQ-0400",
    ),
    Row(
        169,
        "telemetry_report",
        "void",
        "(void)",
        _TELEM_H,
        _TELEM,
        26,
        30,
        5,
        "Format current data-model values for upstream publication.",
        "REQ-0400",
    ),
    # ── src/sound/ ──
    Row(
        123,
        "sound_play_findme",
        "void",
        "(uint8_t mode)",
        _SOUND,
        _SOUND,
        13,
        18,
        13,
        "Play the find-me locating chime.",
        "REQ-0621",
    ),
    Row(
        164,
        "sound_play_findme",
        "void",
        "(uint8_t mode)",
        _SOUND_H,
        _SOUND,
        13,
        18,
        10,
        "Play the find-me locating chime.",
        "REQ-0621",
    ),
    # ── test/ — the @req-tagged, test_*-named function req_test_edges keys on ──
    Row(
        161,
        "test_findme_chime_plays",
        "static void",
        "(void)",
        _TEST,
        _TEST,
        12,
        17,
        12,
        "Verify the find-me chime plays for SOUND_FINDME mode.",
        "REQ-0621",
    ),
    Row(171, "main", "int", "(void)", _TEST, _TEST, 25, 29, 25, "Test-runner entry point."),
    # ── src/legacy/ — a mutually-recursive pair with NO external caller, and
    #    names matching none of the reachability seed patterns. A LONE uncalled
    #    function is seeded live (zero-non-fuzzy-incoming conservatism); only a
    #    dead CLUSTER stays orphan, which is what keeps both liveness values in
    #    the fixture instead of just 'live'.
    Row(
        146,
        "legacy_adc_selftest",
        "static int",
        "(void)",
        _LEGACY,
        _LEGACY,
        22,
        26,
        22,
        "Run the rev-A ADC calibration self-test.",
        "REQ-0900",
        version="1.2",
    ),
    Row(
        147,
        "legacy_adc_trim",
        "static int",
        "(int32_t measured_mv)",
        _LEGACY,
        _LEGACY,
        35,
        48,
        35,
        "Trim the ADC offset toward the reference voltage.",
        "REQ-0900",
        version="1.1",
    ),
    # ── gen/ingot/ — per-key accessors: the key is in the NAME, so the setter
    #    takes exactly one argument and the getter none. That arity is what
    #    separates them from the `...ByKey` dispatchers below.
    Row(
        14,
        "DataModel_Get_DEMOBOT_UX_SOUND_EVENT",
        "static inline uint32_t",
        "(void)",
        _HELPERS,
        _HELPERS,
        13,
        17,
        13,
    ),
    Row(
        25,
        "DataModel_Set_DEMOBOT_POWER_BATTERY_MV",
        "static inline DM_RETURN_CODE",
        "(int16_t x)",
        _HELPERS,
        _HELPERS,
        25,
        30,
        25,
    ),
    Row(
        24,
        "DataModel_Get_DEMOBOT_POWER_BATTERY_MV",
        "static inline int16_t",
        "(void)",
        _HELPERS,
        _HELPERS,
        33,
        37,
        33,
    ),
    # ── gen/ingot/ — the argument-keyed dispatchers, and the lock they take.
    Row(
        17,
        "DataModel_SetIntegralTypeByKey",
        "DM_RETURN_CODE",
        "(dm_key_t key, const dm_val_t *value)",
        _DM_C,
        _DM_C,
        21,
        33,
        21,
        "Store a keyed integral value and fire the change callback.",
    ),
    Row(
        96,
        "DataModel_SetIntegralTypeByKey",
        "DM_RETURN_CODE",
        "(dm_key_t key, const dm_val_t *value)",
        _DM_H,
        _DM_C,
        21,
        33,
        22,
        "Store a keyed integral value and fire the change callback.",
    ),
    Row(
        15,
        "DataModel_GetIntegralTypeByKey",
        "dm_val_t",
        "(dm_key_t key)",
        _DM_C,
        _DM_C,
        41,
        50,
        41,
        "Read a keyed integral value out of the store.",
    ),
    Row(
        97,
        "DataModel_GetIntegralTypeByKey",
        "dm_val_t",
        "(dm_key_t key)",
        _DM_H,
        _DM_C,
        41,
        50,
        23,
        "Read a keyed integral value out of the store.",
    ),
    Row(
        16,
        "DataModel_Initialize",
        "void",
        "(dm_change_cb_t cb)",
        _DM_C,
        _DM_C,
        57,
        60,
        57,
        "Register the change callback fired on every successful set.",
    ),
    Row(
        98,
        "DataModel_Initialize",
        "void",
        "(dm_change_cb_t cb)",
        _DM_H,
        _DM_C,
        57,
        60,
        24,
        "Register the change callback fired on every successful set.",
    ),
    Row(
        62,
        "IntegerStorage_SetUINT8Key",
        "DM_RETURN_CODE",
        "(dm_key_t key, uint8_t value)",
        _STORE_C,
        _STORE_C,
        16,
        23,
        16,
        "Write one keyed byte into the backing store.",
    ),
    Row(
        104,
        "IntegerStorage_SetUINT8Key",
        "DM_RETURN_CODE",
        "(dm_key_t key, uint8_t value)",
        _STORE_H,
        _STORE_C,
        16,
        23,
        8,
        "Write one keyed byte into the backing store.",
    ),
    Row(
        63,
        "IntegerStorage_GetUINT8Key",
        "DM_RETURN_CODE",
        "(dm_key_t key, uint8_t *out)",
        _STORE_C,
        _STORE_C,
        32,
        39,
        32,
        "Read one keyed byte out of the backing store.",
    ),
    Row(
        105,
        "IntegerStorage_GetUINT8Key",
        "DM_RETURN_CODE",
        "(dm_key_t key, uint8_t *out)",
        _STORE_H,
        _STORE_C,
        32,
        39,
        9,
        "Read one keyed byte out of the backing store.",
    ),
)

## Non-function rows: macros, file-scope variables and typedefs that really are in
## `csample`. They carry no body extent and no requirement — their only job is to
## make the `kind='function'` filter every query applies do actual work. Without
## them `search`, `resolve_symbol` and the liveness pass would all be filtering a
## table in which every row already qualifies.
NON_FUNCTIONS: tuple[Row, ...] = (
    ## Every `expansion` below is the literal text after the macro name in
    ## `tests/data/csample/`, so the fixture agrees with the source it claims to
    ## mirror and a test asserting one is asserting a real `#define`.
    Row(
        200,
        "DM_KEY_DEMOBOT_POWER_BATTERY_MV",
        "",
        "",
        _KEY_H,
        "",
        0,
        0,
        7,
        kind="macro definition",
        expansion="0u",
    ),
    Row(
        201,
        "DM_KEY_DEMOBOT_UX_SOUND_EVENT",
        "",
        "",
        _KEY_H,
        "",
        0,
        0,
        8,
        kind="macro definition",
        expansion="1u",
    ),
    Row(
        202, "EVENT_QUEUE_DEPTH", "", "", _BUS, "", 0, 0, 7, kind="macro definition", expansion="8"
    ),
    Row(
        203, "DEMO_LOOP_PASSES", "", "", _MAIN, "", 0, 0, 9, kind="macro definition", expansion="3"
    ),
    Row(204, "SOUND_FINDME", "", "", _SOUND_H, "", 0, 0, 8, kind="macro definition", expansion="1"),
    Row(205, "SOUND_NONE", "", "", _SOUND_H, "", 0, 0, 7, kind="macro definition", expansion="0"),
    Row(
        206, "STORAGE_SLOTS", "", "", _STORE_C, "", 0, 0, 5, kind="macro definition", expansion="2"
    ),
    Row(207, "s_last_sample", "static int16_t", "", _SENSOR, _SENSOR, 0, 0, 9, kind="variable"),
    Row(208, "s_reports_sent", "static int", "", _TELEM, _TELEM, 0, 0, 9, kind="variable"),
    Row(209, "s_cmd_handler", "static event_handler_t", "", _BUS, _BUS, 0, 0, 12, kind="variable"),
    Row(210, "dm_mutex", "static pthread_mutex_t", "", _DM_C, _DM_C, 0, 0, 11, kind="variable"),
    Row(211, "s_change_cb", "static dm_change_cb_t", "", _DM_C, _DM_C, 0, 0, 12, kind="variable"),
    Row(212, "event_t", "", "", _BUS_H, "", 0, 0, 15, kind="typedef"),
    Row(213, "event_handler_t", "", "", _BUS_H, "", 0, 0, 17, kind="typedef"),
    Row(214, "dm_val_t", "", "", _DM_H, "", 0, 0, 18, kind="typedef"),
    Row(215, "event_id_t", "", "", _BUS_H, "", 0, 0, 9, kind="enumeration"),
)


# ─── the inline xrefs Layer 1 reads ──────────────────────────────────────────

## One logical call edge per entry, as (caller, callee name). A `str` caller
## expands over EVERY memberdef row of that name; an `int` caller pins one rowid,
## which is how the two different `main`s are told apart.
##
## Doxygen emits an inline xref for the cartesian product of the caller's rows and
## the callee's rows, so a call from a function that also has a header declaration
## produces two rows and a call INTO one produces two more. That is not an
## artefact to be tidied away — it is the decl/def duality the query layer's
## definition-preferring resolution exists to correct, and a fixture that emitted
## one clean row per edge would delete the thing under test.
XREF_EDGES: tuple[tuple[str | int, str], ...] = (
    ("app_run", "event_bus_publish"),
    ("app_run", "sensor_poll"),
    ("app_run", "event_bus_dispatch"),
    (119, "event_bus_init"),
    (119, "dm_event_dispatch_init"),
    (119, "sensor_init"),
    (119, "telemetry_init"),
    (119, "command_handler_init"),
    (119, "app_run"),
    ("command_handler_init", "event_bus_subscribe_cmd"),
    ("handle_cloud_command", "telemetry_report"),
    ("handle_dm_key_event", "DataModel_Get_DEMOBOT_UX_SOUND_EVENT"),
    ("handle_dm_key_event", "sound_play_findme"),
    ("dm_event_dispatch_init", "DataModel_Initialize"),
    ("sensor_poll", "hw_read_battery_adc"),
    ("sensor_poll", "DataModel_Set_DEMOBOT_POWER_BATTERY_MV"),
    ("telemetry_report", "DataModel_Get_DEMOBOT_POWER_BATTERY_MV"),
    ("test_findme_chime_plays", "sound_play_findme"),
    (171, "test_findme_chime_plays"),
    ("legacy_adc_selftest", "legacy_adc_trim"),
    ("legacy_adc_trim", "legacy_adc_selftest"),
    ("DataModel_Set_DEMOBOT_POWER_BATTERY_MV", "DataModel_SetIntegralTypeByKey"),
    ("DataModel_Get_DEMOBOT_POWER_BATTERY_MV", "DataModel_GetIntegralTypeByKey"),
    ("DataModel_Get_DEMOBOT_UX_SOUND_EVENT", "DataModel_GetIntegralTypeByKey"),
    ("DataModel_SetIntegralTypeByKey", "IntegerStorage_SetUINT8Key"),
    ("DataModel_GetIntegralTypeByKey", "IntegerStorage_GetUINT8Key"),
)


## @brief Rows of a name, or the single row of an explicit rowid.
## @param spec A function name (every row) or a memberdef rowid (that row only).
## @return The matching memberdef rowids, ascending.
## @version 1
def _rowids(spec: str | int) -> list[int]:
    """@brief Resolve an edge endpoint spec to memberdef rowids.

    @param spec Function name or explicit rowid.
    @return Ascending rowids.
    @version 1
    """
    if isinstance(spec, int):
        return [spec]
    return sorted(row.rowid for row in FUNCTIONS if row.name == spec)


## @brief Every (caller_rowid, callee_rowid) pair the declared edges expand to.
## @return Sorted, de-duplicated rowid pairs.
## @version 1
def edge_rowid_pairs() -> list[tuple[int, int]]:
    """@brief Expand XREF_EDGES over the decl/def rows of both endpoints.

    @return Sorted unique (caller_rowid, callee_rowid) pairs.
    @version 1
    """
    pairs = {
        (caller, callee)
        for caller_spec, callee_name in XREF_EDGES
        for caller in _rowids(caller_spec)
        for callee in _rowids(callee_name)
    }
    return sorted(pairs)


## @brief The doxygen description text carrying a version and an optional @req.
## @param row The memberdef row being described.
## @return The `detaileddescription` column text.
## @version 1
def _detailed(row: Row) -> str:
    """Reproduces the shape doxygen really writes, which matters twice over:
    `extract_version` parses the `<simplesect kind="version">` wrapper, and
    `import_req_edges` finds the LITERAL `@req <id>` that doxygen passes through
    into the description when the tag has no xrefitem alias. A fixture that stored
    a bare id would leave both parsers untested.

    @brief Build a doxygen-shaped detaileddescription.
    @param row The memberdef row being described.
    @return Description markup.
    @version 1
    """
    if not row.version:
        return ""
    req = f" @req {row.req}" if row.req else ""
    return (
        f'<para><simplesect kind="version"><para>{row.version}{req} </para>\n'
        "</simplesect>\n</para>\n"
    )


## @brief Insert the doxygen-owned `path` rows.
## @param conn Open connection to the database being built.
## @version 1
def _insert_paths(conn: sqlite3.Connection) -> None:
    """@brief Write the file, system-header, synthetic and directory path rows.

    @param conn Open connection.
    @version 1
    """
    rows = [(rowid, _TYPE_FILE, 1, 1, name) for rowid, name in FILE_PATHS.items()]
    rows += [(rowid, _TYPE_FILE, 0, 0, name) for rowid, name in SYSTEM_PATHS.items()]
    rows += [(rowid, _TYPE_FILE, 0, 0, name) for rowid, name in SYNTHETIC_PATHS.items()]
    rows += [(rowid, _TYPE_DIR, 1, 1, name) for rowid, name in DIR_PATHS.items()]
    conn.executemany(
        "INSERT INTO path (rowid, type, local, found, name) VALUES (?, ?, ?, ?, ?)",
        rows,
    )


## @brief Insert the doxygen-owned `memberdef` and `refid` rows.
## @param conn Open connection to the database being built.
## @version 1
def _insert_memberdefs(conn: sqlite3.Connection) -> None:
    """`refid` is populated too, because `memberdef.rowid` carries a foreign key
    into it and the XML-refid resolution path reads it. Cheap, and it keeps the
    fixture from being a database doxygen would never emit.

    @brief Write every memberdef row plus its refid.
    @param conn Open connection.
    @version 1
    """
    for row in (*FUNCTIONS, *NON_FUNCTIONS):
        conn.execute(
            "INSERT INTO refid (rowid, refid) VALUES (?, ?)",
            (row.rowid, f"fixture_{row.rowid}"),
        )
        conn.execute(
            "INSERT INTO memberdef (rowid, name, definition, argsstring, kind, static, "
            "bodystart, bodyend, bodyfile_id, file_id, line, column, "
            "briefdescription, detaileddescription, initializer) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                row.rowid,
                row.name,
                row.definition,
                row.args,
                row.kind,
                row.static,
                row.start,
                row.end,
                _PATH_ROWID[row.body] if row.body else None,
                _PATH_ROWID[row.file],
                row.line,
                1,
                f"<para>{row.brief} </para>\n" if row.brief else "",
                _detailed(row),
                row.expansion,
            ),
        )


## @brief Insert the inline `xrefs` rows Layer 1 imports from.
## @param conn Open connection to the database being built.
## @version 1
def _insert_xrefs(conn: sqlite3.Connection) -> None:
    """`context='inline'` is doxygen's own marker for "referenced from inside a
    function body", which is the closest thing its sqlite3 backend has to a call
    edge — so writing these and letting `build_call_edges` derive the
    `doxygen_sqlite` layer keeps Layer 1 a REAL stage rather than a table of
    pre-computed answers.

    @brief Write one inline xref per expanded edge pair.
    @param conn Open connection.
    @version 1
    """
    conn.executemany(
        "INSERT INTO xrefs (src_rowid, dst_rowid, context) VALUES (?, ?, 'inline')",
        edge_rowid_pairs(),
    )


## @brief Create the doxygen-owned tables and fill them.
## @param db Path to the database file to create.
## @version 1
def seed_doxygen_tables(db: Path) -> None:
    """The whole hand-made half of the fixture, and the only half. Loads doxygen's
    verbatim schema, then writes the `path`, `refid`, `memberdef` and `xrefs` rows
    a real doxygen run would have produced for `tests/data/csample/`.

    @brief Build the doxygen half of the synthetic index.
    @param db Database path to create.
    @version 1
    """
    conn = sqlite3.connect(str(db))
    try:
        conn.executescript(DOXYGEN_SCHEMA.read_text(encoding="utf-8"))
        _insert_paths(conn)
        _insert_memberdefs(conn)
        _insert_xrefs(conn)
        conn.commit()
    finally:
        conn.close()


## @brief Run every derivable pipeline stage against the seeded index.
## @param db Path to the seeded database.
## @param repo_root The real source tree the index describes.
## @version 3
def run_real_stages(db: Path, repo_root: Path) -> None:
    """Stage ORDER mirrors `cli._build_stages` and is load-bearing in several
    places: the thread-membership closure and the reachability BFS both need the
    complete non-fuzzy call graph (fnptr edges included), and
    `annotate_thread_boundaries` has to run after every shared-key row exists.

    THREE STAGES THAT CREATE SCHEMA WERE MISSING UNTIL gh#362, and the tier caught it
    exactly as designed: `import_kconfig_gates` (gh#18) creates `kconfig_gates` and
    its `form` CHECK, `ingest_file_docs` (gh#10) creates `file_docs`, and
    `recover_ast_symbols` (gh#11) ADDs `memberdef.dg_source` with its CHECK. A
    fixture without them cannot represent the provenance filter every later test
    depends on — `dg_source = 'doxygen'` is what stops a recovered symbol answering
    for the mechanism under test — so their absence was a silent licence to assert
    over a schema that does not ship. They add 11 `file_docs` rows and 0
    `kconfig_gates` rows on `csample` (the table must still EXIST while empty).
    Their positions mirror the CLI's — gates and recovery above every call-edge layer,
    `file_docs` below prose ingestion, which DROPs the table it shares.

    THE REASON FOR THAT ZERO CHANGED, and the old one was the gh#390 defect written down
    as expected behaviour: this said the table was "correctly EMPTY" because `csample`
    "declares no Kconfig". It was actually empty because the harvest matched a hardcoded
    `CONFIG_` prefix, which no C repository outside Kconfig uses. When the harvest widened,
    `csample` produced 10 gating symbols — every one an INCLUDE GUARD, which is not a
    configuration gate and is now excluded structurally. So the count is zero again, for a
    reason that is true: this fixture gates nothing on configuration. If a real
    `#if defined(...)` is ever added to `csample`, this number MUST move.

    `recover_ast_symbols` USED TO RECOVER NOTHING HERE, and that was recorded as a
    property of `csample` — every function in it is already a hand-made `memberdef`
    row. gh#372 gave the stage a second kind and it now adds SIX `kind='variable'`
    rows: the file-scope statics in `event_bus.c`, `legacy_calibration.c` and
    `integer_storage.c`, which no hand-made row covers. The fixture is better for it —
    an all-doxygen `memberdef` could not represent the `dg_source = 'doxygen'` filter
    that later tests rely on, so a control asserting an all-doxygen split was passing
    for a reason unrelated to what it claimed (see
    `test_graph_stats.test_symbol_provenance_is_a_measured_distribution_or_nothing`).

    Deliberately absent: the declared-dispatch / MQTT / event-edge stages
    (nothing in `csample` declares them, and they create no tables of their own),
    and the enrichment pass (opt-in, `--enrich` only).

    @brief Execute the real, filesystem-driven half of the pipeline.
    @param db Database path.
    @param repo_root Source tree root.
    @version 3
    """
    from clew.ast_symbols import recover_ast_symbols
    from clew.call_edges import build_call_edges, import_ast_call_edges
    from clew.callback_edges import import_callback_registration_edges
    from clew.datamodel import import_data_model_keys
    from clew.filedocs import ingest_file_docs
    from clew.kconfig_gates import import_kconfig_gates
    from clew.locks import extract_locks
    from clew.prose import ingest_supplementary_docs
    from clew.reachability import mark_reachability
    from clew.requirements import (
        import_req_edges,
        import_req_test_edges,
        ingest_requirements_yaml,
        load_guard_config,
        resolve_req_id_pattern,
    )
    from clew.shared_key_edges import (
        import_shared_key_edges_declared,
        import_shared_key_edges_inferred,
    )
    from clew.signature import write_build_signature
    from clew.testscope import TEST_PATH_FACTS, mark_test_scope
    from clew.threads import annotate_thread_boundaries, extract_threads

    ingest_supplementary_docs(db, repo_root)
    import_kconfig_gates(db, repo_root)
    recover_ast_symbols(db, repo_root)
    ingest_file_docs(db, repo_root)
    build_call_edges(db)
    import_ast_call_edges(db, repo_root)
    import_callback_registration_edges(db, repo_root)
    extract_locks(db, repo_root)
    extract_threads(db, repo_root)
    import_shared_key_edges_inferred(db, repo_root, None)
    import_shared_key_edges_declared(db, repo_root / "data_model_keys.yaml")
    annotate_thread_boundaries(db)
    ## gh#351 creates `data_model_keys`, and the fidelity tier caught its absence the same way
    ## it caught the three gh#362 found — a fixture missing a shipped table is a licence to
    ## assert over a schema that does not exist. `csample` declares no ingot/UDM manifest, so
    ## the table is correctly EMPTY here and must still EXIST. Position mirrors the CLI's,
    ## below the shared-key layers.
    import_data_model_keys(db, repo_root, ())
    # Via the SAME unified discovery the CLI uses (gh#16), not a third copy of the
    # root literal — a helper that hardcodes what production discovers cannot
    # exercise the discovery, so a subdir-config regression would pass here.
    from clew.precommit import discover_guard_config

    guard_cfg = load_guard_config(discover_guard_config(repo_root).path)
    ingest_requirements_yaml(db, repo_root / "requirements.yaml", guard_cfg)
    import_req_edges(db, resolve_req_id_pattern(guard_cfg))
    import_req_test_edges(db)
    mark_reachability(db)
    ## Runs the REAL stage with the REAL defaults, like every other stage here — the
    ## fixture-fidelity gate compares this database's table set against a live build, and
    ## it caught `test_scope` missing the moment the stage was added to the pipeline. A
    ## fixture that hand-rolls the table instead would be free to drift from it.
    with sqlite3.connect(db) as _ts:
        mark_test_scope(_ts, list(TEST_PATH_FACTS))
    write_build_signature(db)


## @brief Build the complete synthetic index at `db`.
## @param db Path the database should be created at.
## @param repo_root The source tree the index describes.
## @version 1
def build_rich_db(db: Path, repo_root: Path = CSAMPLE) -> Path:
    """@brief Seed doxygen's tables, then run every derivable pipeline stage.

    @param db Database path to create.
    @param repo_root Source tree the index describes.
    @return The database path.
    @version 1
    """
    seed_doxygen_tables(db)
    run_real_stages(db, repo_root)
    return db
