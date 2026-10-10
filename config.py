"""Everything you're likely to edit lives in this one file.

Change a value, then run `python build_card.py --offline` to preview locally, or just push:
the GitHub Action rebuilds both SVGs on every push to this repo and once a day.
"""
from datetime import date

# -- header + uptime ------------------------------------------------------------
HEADER = "Udhaya Adhithya Varman"   # first line of the card (neofetch style is user@host)
UPTIME_SINCE = date(2004, 10, 4)     # drives the "Uptime" counter: 4 Oct 2004 (day, month, year)

# -- the info panel, top to bottom ------------------------------------------------
#   ("Key", "Value")  ->  ". Key: ............ Value"
#   "Some title"      ->  "- Some title ------------"   (section divider)
#   "@stats"          ->  the live GitHub numbers
#   None              ->  blank line
# Inside a value, {uptime} becomes the live "4 years, 2 months, 8 days" text.
# The panel is 62 characters wide; the build stops with a clear message if a line doesn't fit.
INFO = [
    ("OS", "Windows 11"),
    ("Uptime", "{uptime}"),
    ("Host", "Unizen Technologies"),
    ("Kernel", "AI Engineer (GenAI, ML, Embedded)"),
    ("Education", "CSE (AI), Sathyabama Institute, 2026"),
    ("Stack.AI", "LangGraph, FastAPI, ChromaDB, MCP, Groq"),
    ("Stack.Ops", "Docker, MLflow, GitHub Actions"),
    None,
    ("Languages.Programming", "Python, SQL"),
    ("Languages.Computer", "YAML, JSON, Markdown"),
    ("Languages.Real", "English"),
    None,
    ("Hobbies.Software", "Agentic AI, RAG, MCP servers"),
    ("Hobbies.Hardware", "Embedded systems, edge ML"),
    None,
    "Contact",
    ("Email.Personal", "udhayaadhithyavarman@gmail.com"),
    ("LinkedIn", "linkedin.com/in/udhayaadhithyavarman"),
    None,
    "GitHub Stats",
    "@stats",
]

# -- GitHub numbers -----------------------------------------------------------------
# Which repos count toward "Lines of Code on GitHub" (your own commits on the default branch only):
#   OWNER                repos you own
#   COLLABORATOR         repos you were invited to
#   ORGANIZATION_MEMBER  repos of organizations you belong to, private ones included.
#                        Leave it out unless you want company/org code counted in a public number.
LOC_AFFILIATIONS = ["OWNER", "COLLABORATOR"]
LOC_INCLUDE_FORKS = False

# -- portrait -------------------------------------------------------------------------
ASCII_DARK = "assets/ascii_dark.txt"     # light characters on the dark card
ASCII_LIGHT = "assets/ascii_light.txt"   # dark characters on the light card (falls back to the dark file)
