# SPDX-License-Identifier: MIT
"""The wiki's one modal component, from the Python side (round 3, P1b).

Every page carries one `<dialog id="clew-modal">` (the theme's layout) and `clew.js` drives it.
A page opens it through a TRIGGER naming a KEY: the content is an inert `<template id="modal-KEY">`
written here, which the script clones — repository text is escaped by the caller before it
reaches the template, and the title travels as an escaped attribute, never as markup. The key is
the deep link (`#m=KEY`), so it is restricted to characters a URL fragment carries unescaped.

@brief Build modal triggers and their content templates.
@version 2
"""

from __future__ import annotations

import re
from html import escape

## A key the script's `#m=` reader accepts.
_KEY = re.compile(r"^[\w.:-]+$")


## @brief A trigger and the template it opens.
## @param key The modal key: the deep link `#m=KEY`.
## @param label The trigger's visible text (escaped here).
## @param title The modal's title (escaped here).
## @param body The modal's content: HTML the caller built from escaped text.
## @param cls Extra classes for the trigger.
## @return HTML.
## v2: the template (and its key check) is `modal_template`, shared with SVG triggers.
## @version 2
## @req REQ-DDB-WIKI-020
def modal(key: str, label: str, title: str, body: str, cls: str = "") -> str:
    """@brief Write a trigger + template. @return HTML."""
    classes = f"modal-link {cls}".strip()
    return (
        f'<a class="{classes}" href="#m={key}" data-modal="{key}">{escape(label)}</a>'
        + modal_template(key, title, body)
    )


## @brief The template alone, for a trigger drawn elsewhere (an SVG box carrying `data-modal`).
## @param key The modal key.
## @param title The modal's title (escaped here).
## @param body The modal's content: HTML the caller built from escaped text.
## @return HTML.
## @version 1
## @req REQ-DDB-WIKI-020
def modal_template(key: str, title: str, body: str) -> str:
    """REFUSES a key the hash reader would not accept, rather than writing a template whose deep
    link silently opens nothing.

    @brief Write a template.
    @return HTML.
    """
    if not _KEY.match(key):
        raise ValueError(f"modal key {key!r} must match {_KEY.pattern}")
    return f'<template id="modal-{key}" data-title="{escape(title)}">{body}</template>'
