# Kerb gaps in the NSW top 10 suburbs (19 Nov 2026, thread "Trace 99% of kerbs in NSW top 10")
Owner's goal: get the top 10 NSW suburbs to a usable stage by finding the root causes kerbs fail, one at a time.
- measure.py: usable-kerb measure per suburb (both sides of every built street every 5 m; see its docstring for what is left out).
- cause.py: sums each gap side by the reason kerblot.py left its block blank (--why). sheet.py / plot.py: pictures of gaps.
- fetch.py / fetchin2.py: suburb outlines, lots and roads (with roadnameoid etc.); off.py / offall.py: council kerb lines.
- join3.py: adds the rings both close-up reviewers passed onto the last version (whole rings only).
- close3.py / close4.py: 120 m second-look close-ups with lot lines and centrelines. REVIEW-BRIEF.md: the close-up reviewer's brief.
- get2.sh: downloads ELVIS packages once the links arrive by email.
Result: version nsw-2026-11-19 (OpenFetch main derived-layers/kerbs/nsw-2026-11-19/README.md), case P-0178.
