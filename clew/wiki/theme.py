# SPDX-License-Identifier: MIT
"""The site's theme: clew's default (the sassafras-class look) or any installed Sphinx theme.

1.4.0 W13 (owner 2026-11-15: "I recommend sassafras-class theme as a default, customization
allowed to end repo"). The default theme, `clew`, ships inside this package
(`themes/clew`: a `basic`-derived layout and `clew.css`), with the three OFL faces it is drawn in
(`themes/fonts`, licence texts beside them). Every asset is copied into the site's `_static`, so
the site stays self-contained: no CDN, no font service.

A repository customises it through `wiki.theme`:
  * `palette` — any of `config.THEME_TOKENS`, written to `_static/clew-theme.css` after `clew.css`
    so it wins in both colour schemes;
  * `css` — extra stylesheets, copied into `_static` and linked last;
  * `logo` — shown in the top bar;
  * `fonts: false` — no font files; the CSS falls back to system faces;
  * `name` — another installed Sphinx theme, in which case NOTHING ELSE is imposed on it.

@brief Sphinx settings and static files for the site's theme.
@version 1
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from .config import ThemeSpec

## The package directory holding the default theme and its fonts.
THEMES = Path(__file__).parent / "themes"


## @brief The conf.py settings for a theme, its static files copied into the source tree.
## @param spec The theme declaration.
## @param repo_root The repository (the declaration's paths are relative to it).
## @param source The Sphinx source directory; `_static` is created in it.
## @return {conf.py name: value}.
## @version 1
## @req REQ-DDB-WIKI-011
def sphinx_settings(spec: ThemeSpec, repo_root: Path, source: Path) -> dict[str, Any]:
    """A NAMED THEME IS TAKEN AS IT IS: its own look, the repository's extra stylesheets and logo
    only. The palette and fonts belong to clew's theme and are not forced onto another.

    @brief Build theme settings.
    @return Settings.
    """
    static = Path(source) / "_static"
    static.mkdir(parents=True, exist_ok=True)
    settings: dict[str, Any] = {"html_theme": spec.name, "html_static_path": ["_static"]}
    css: list[str] = []
    if spec.name == "clew":
        settings["html_theme_path"] = [str(THEMES)]
        css += _clew_assets(spec, static)
    for rel in spec.css:
        shutil.copyfile(Path(repo_root) / rel, static / Path(rel).name)
        css.append(Path(rel).name)
    if spec.logo:
        shutil.copyfile(Path(repo_root) / spec.logo, static / Path(spec.logo).name)
        settings["html_logo"] = f"_static/{Path(spec.logo).name}"
    settings["html_css_files"] = css
    return settings


## @brief Copy the default theme's fonts and write the palette overrides.
## @param spec The theme declaration.
## @param static The source tree's `_static`.
## @return Stylesheets to link, in order.
## @version 1
## @dg_internal
def _clew_assets(spec: ThemeSpec, static: Path) -> list[str]:
    """THE OVERRIDE SELECTOR MATCHES the dark scheme's, so a token a repository sets applies in
    both colour schemes rather than only in light.

    @brief Fonts and palette.
    @return Stylesheets.
    """
    css = []
    if spec.fonts:
        shutil.copytree(THEMES / "fonts", static / "fonts", dirs_exist_ok=True)
        css.append("fonts/clew-fonts.css")
    if spec.palette:
        tokens = ";".join(f"--{k}:{v}" for k, v in spec.palette)
        (static / "clew-theme.css").write_text(
            f':root,:root:not([data-theme="light"]){{{tokens}}}\n', encoding="utf-8"
        )
        css.append("clew-theme.css")
    return css
