# Vid2Spatial: web demo

Browser demo for **Vid2Spatial** (IEEE ISMAR 2026 Poster #5498, Seoul National University).
Draw one box on a video and hear the extracted azimuth / elevation / distance stream rendered binaurally, or sketch a trajectory by hand.

**Live demo:** https://paiiek.github.io/vid2spatial-demo/ (headphones required)

This repository contains only the demo page. The extraction engine is not open-sourced; for research inquiries, contact the authors.

`web_demo/build.py` assembles `docs/index.html` (self-contained) from `web_demo/index.template.html` and `web_demo/assets/`.
