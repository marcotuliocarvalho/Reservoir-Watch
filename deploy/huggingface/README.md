---
title: Reservoir Watch
emoji: 💧
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
short_description: Brazil's SIN reservoirs from ONS open data
---

# Reservoir Watch (demo)

Online demo of the [Reservoir Watch](https://github.com/marcotuliocarvalho/Reservoir-Watch)
dashboard: storage levels, criticality alerts and flows of the reservoirs of
Brazil's National Interconnected System (SIN), built on open data from
[ONS](https://dados.ons.org.br).

The image runs the ingestion pipeline at build time, so the data is as fresh
as the last build. A GitHub Actions job rebuilds this Space every day.

This Space is deployed from GitHub. Do not edit it here: changes are
overwritten on the next deploy.
