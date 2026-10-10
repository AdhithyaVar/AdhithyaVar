# Profile card setup

Neofetch-style GitHub profile card: ASCII portrait on the left, your details and live GitHub numbers on the right.
Two SVGs (`dark_mode.svg`, `light_mode.svg`) are rebuilt every day by a GitHub Action, and `README.md` shows the
right one for the viewer's light or dark theme.

## 1. Make the profile repo

1. On GitHub, create a **public** repository named exactly like your username (`<username>/<username>`).
2. Copy everything in this folder into it and push to `main`.

## 2. Give the Action a token

1. https://github.com/settings/tokens -> *Generate new token (classic)*. Scopes: `repo`, `read:user`.
   Add `read:org` only if you put `ORGANIZATION_MEMBER` in `LOC_AFFILIATIONS` (config.py).
2. In the new repo: *Settings -> Secrets and variables -> Actions -> New repository secret*.
   Name `ACCESS_TOKEN`, value = the token.
3. *Actions* tab -> *Update profile card* -> *Run workflow*. The first run reads every commit you authored, so give
   it a few minutes. Later runs only re-read repos whose commit count changed.

Private repos count toward the totals and only the totals are published. The cache in `cache/` stores hashed repo
names, never real ones, and the Action log never prints repo names.

## 3. Make it yours

- **config.py** - header, uptime start date, every line of the info panel. Replace the contact placeholders.
- **Portrait** - `pip install pillow`, then `python make_ascii.py your-photo.jpg`. Tune with `--cols 64`,
  `--crop 100,0,900,1000`, `--contrast 1.5`, `--gamma 1.2`. This replaces the placeholder silhouette in `assets/`.
  A transparent-background PNG gives the cleanest result. Keep the photo itself out of the repo.
- **Preview, no network** - `python build_card.py --offline`, then open `dark_mode.svg` in a browser.
  `python build_card.py --demo` writes made-up numbers to `preview/` so you can see a filled card.
- **Live numbers locally** - `pip install -r requirements.txt`, set `ACCESS_TOKEN` and `USER_NAME`, run
  `python build_card.py`. PowerShell: `$env:ACCESS_TOKEN="ghp_..."; $env:USER_NAME="your-username"`.

## Troubleshooting

- Action fails with HTTP 401 or 403: token expired, wrong scopes, secret misnamed, or a rate limit. Re-run later.
- Numbers show `--`: the Action has not succeeded yet.
- "a line is too long": the info panel is 62 characters wide. Shorten that value in `config.py`.
- Lines of Code shows an old value after a warning in the log: that step failed once and kept the last good
  number. Run the build locally to see the full error.
- Card stops updating after months of no activity: GitHub pauses scheduled workflows on idle public repos.
  Re-enable it from the *Actions* tab.
