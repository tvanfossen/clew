<!-- SPDX-License-Identifier: MIT -->
# Machine: `i7-7700k-ubuntu2204`

Characterised 2026-10-18, before the first published acceptance grid. Every figure in this
directory and **every time-axis number in a grid run on this machine** is bound to what is below.

This is the first machine directory in the tree. `README.md` has stated since it was written that
*"the figures cited above were taken on a machine that was never characterised, which is itself
the defect this layout exists to prevent"* — so until now the operational figures, and the time
axis of any grid, were not citable. This file is what makes them so, and it says nothing about
whether the numbers are good.

## Hardware

| | |
|---|---|
| CPU | Intel Core i7-7700K @ 4.20 GHz (max 4.50 GHz) |
| Topology | 1 socket · 4 cores · 2 threads/core · **8 logical** |
| RAM | 31 GiB |
| Storage | Samsung SSD 850 EVO 500 GB, SATA, `rotational=0`, ext4 |
| Root filesystem | 457 G total |

**A 2017 desktop part, and that matters for how these figures read.** Four physical cores means a
cold build is near-serial in practice once doxygen and the parse pass are both resident, and a
figure taken here is a floor rather than a representative value. It is also not a laptop: no
thermal or power governor moves under a long run, so a ten-hour grid does not drift the way a
portable machine's would.

## Software

| | |
|---|---|
| OS | Ubuntu 22.04.5 LTS, kernel 6.8.0-138-generic |
| Python | 3.10.12 (`.venv`) |
| doxygen | 1.18.0 (`8e760943e5d9581a444cf327f43a0b4d20d29482`) |

## What is NOT pinned here

**Free disk space, which moves.** 53 G free at characterisation against 457 G total. A grid
provisions a shallow checkout and a full index per target, and the doxygen intermediates on the
larger trees are the real consumers — so free space is a run-time precondition to check, not a
property of the machine. It is recorded per run, not here.

**Memory headroom, for the same reason.** 31 GiB total but 5.7 GiB available under ordinary
desktop load at characterisation. This bounds grading concurrency rather than anything about the
tool: each judge call spawns its own CLI process, so `grade --jobs` is limited by free memory on
this machine well before it is limited by the eight threads.

**Load.** Load average 2.3 over the preceding minute, on an attended desktop that is in use. A
figure taken here is not taken on an idle machine, and nothing in this layout pretends otherwise.
The honest consequence is that the time axis of a grid run here carries noise of unmeasured size
from whatever else the operator was doing — which is one more reason
`acceptance/DESIGN.md` keeps refresh latency out of the matrix entirely.

## Still missing from this directory

`build-cold.md`, `refresh-curve.md` and `estimator-accuracy.md`, which the layout above calls
for. Characterising the machine does not measure it. The estimator-accuracy gap is the one that
decides a policy — `README.md` names it *"the measurement that actually decides the policy"* —
and it remains unmeasured on this machine as on every other.
