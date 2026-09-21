# Supplemental materials: Vid2Spatial (ISMAR 2026 Poster #5498)

Materials listed under "Supplemental materials" in the paper.

| Folder | Contents |
|---|---|
| `trajectories/` | The `traj.json` streams behind every listening-test stimulus (10 LaSOT clips) and the Sec. 6 runtime measurement (`tank-8`). Unedited tracker output: per frame `az`, `el` (rad), `d_rel`, `dist_m`, mask centroid `cx, cy`, box `w, h`, `confidence`; header `fps`, `intrinsics` (60° FOV). |
| `data/listening_test/` | Anonymized ratings (N = 20, 10 clips × 3 conditions × Q1–Q4) and per-listener clip / condition order. |
| `data/efficiency_study/` | Anonymized trial logs of the authoring study (N = 12): times, edit counts, questionnaires, authored trajectories. |
| `analysis/` | Scripts that reproduce the reported statistics. |
| `results/` | Their outputs as reported in the paper. |

**Listening-test stimuli** (WAV + video, 124 MB) are attached to the GitHub release
[`supplemental-v1`](https://github.com/paiiek/vid2spatial-demo/releases/tag/supplemental-v1):
per clip `mono`, `baseline` (C-BASE, stereo pan), `nodepth` (C-NODEP, HRTF direction only)
and `proposed` (C-PROP, HRTF + distance).

## Reproduce

```bash
pip install numpy scipy python-osc
python analysis/analyze_listening_test.py      # Sec. 5: Friedman + Bonferroni Wilcoxon
python analysis/run_equivalence_tost.py        # Sec. 7: non-inferiority / TOST on satisfaction
python analysis/run_mr_loop_bench.py \
       --traj trajectories/tank-8.traj.json    # Sec. 6: OSC authoring-to-runtime latency
```

The latency figure depends on the machine; the paper's run is `results/mr_loop_bench.json`.

Video clips are from LaSOT (Fan et al., CVPR 2019). Participants' identities and free-text comments are removed.
