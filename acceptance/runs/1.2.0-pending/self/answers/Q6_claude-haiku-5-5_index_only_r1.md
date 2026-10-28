**Short answer:** for shell, CMake, YAML and JSON, clew indexes only what each file type can honestly give it. Shell and CMake get function-level symbols. YAML and JSON get a file-level row and nothing else. If the installed parser lacks these grammars, the shell and CMake symbols disappear, the files stay findable by name, and the empty-answer report says which file types were not read. I answered from the index alone, so I did not check whether the build that produced this index had the grammars.

**What the index holds**

| File type | Rows written | What you can ask |
|---|---|---|
| `.sh`, `.bash` | `path` row plus `memberdef` for each shell function | Function names; docs taken from the `#` block directly above the definition |
| `CMakeLists.txt`, `.cmake` | `path` row plus `memberdef` for each `function` and `macro` | Function names; macros recorded as macros |
| `.yaml`, `.yml`, `.json` | `path` row only | Whether the file exists in the index and can be found by name |

Shell and CMake definitions are written by `clew/synth.py`, which adds rows after doxygen runs and uses the same table shapes doxygen uses. The definitions stage runs before call resolution, so these rows can be call targets in principle. I did not confirm that shell or CMake call sites produce call edges.

**What the index does not hold**

- **YAML and JSON have no symbols.** Their grammars only offer key/value pair nodes. The design notes say that writing those keys as `memberdef` rows would flood `dossier("my_function")` with every `steps:` key in every workflow file. So they are registered and never harvested.
- **Shell and CMake are limited to definitions.** The index records functions and macros only. The CMake dialect's own description says `CMakeLists.txt` is where a repo states what it builds, with which flags and dependencies, and doxygen does not read it. Nothing I could see indexes targets, flags, or dependencies, so I cannot say they are captured.
- **Top-level shell commands and variables** are not mentioned anywhere as indexed.

**What happens without the grammars**

The published `lang-parsing-substrate` 0.11.2 wheel lacks the bash, cmake, yaml, json and markdown grammars. The fork that has them also reports 0.11.2, so version checks cannot tell them apart. clew therefore asks whether each grammar is compiled in, not which version is installed.

On the published wheel:

1. **No crash.** The router checks capability before parsing. Without the check, a missing grammar would raise `ValueError: unknown language key` mid-build.
2. **Shell and CMake degrade to YAML/JSON behaviour.** The file gets a `path` row and no symbols.
3. **Empty answers are explained.** The build counts in-scope files of each missing type and stamps that count, so a miss can say something like "14 `.sh` files were in scope and none are in this index." The caller then knows to read the file directly rather than conclude the function does not exist. An index built before this release stamps nothing, so its empty answers look like plain absence.
4. **A broken substrate install is logged, not fatal.** It yields no languages. The pre-commit gate also goes through this path, so it stays up and reports the gap.