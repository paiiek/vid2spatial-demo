#!/usr/bin/env python3
"""Assemble index.html from index.template.html + assets/ (all inlined as base64,
so the page is one self-contained file for GitHub Pages)."""
import base64, json, os
ROOT = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(ROOT, "assets")
CLIPS = ["car-10", "drone-13", "skateboard-8", "dog-1"]

def b64(p):
    return base64.b64encode(open(p, "rb").read()).decode()

def main():
    clips = {c: {"video": b64(f"{ASSETS}/{c}.mp4"), "mono": b64(f"{ASSETS}/{c}.mono.m4a"),
                 "kemar": b64(f"{ASSETS}/{c}.kemar.m4a"), "traj": json.load(open(f"{ASSETS}/{c}.traj.json"))}
             for c in CLIPS}
    arch = "data:image/jpeg;base64," + b64(f"{ASSETS}/figure_arch.jpg")
    html = open(os.path.join(ROOT, "index.template.html")).read()
    html = html.replace("{{ASSETS}}", json.dumps({"clips": clips}, separators=(",", ":"))).replace("{{ARCH_IMG}}", arch)
    out = os.path.join(ROOT, "..", "docs", "index.html")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    open(out, "w").write(html)
    print(out, os.path.getsize(out) // 1024, "KB")

if __name__ == "__main__":
    main()
