# Direct-outline/all-history baseline

This experiment uses the exact frozen `generation_assets.json` shared by all six
trajectories in `full_scene_gate_ab_v1`. For episode N, Qwen3.6 receives the
world view, character settings, story outline, current episode outline, and the
verbatim scripts generated for baseline episodes 1 through N-1.

The baseline deliberately excludes scene-outline generation, narrative memory,
state lifecycle memory, obligations, hybrid retrieval, Strategy cards, state
gates, plot-library retrieval, and post-generation rewriting.

R01, R02, and R03 are independent stochastic runs. Episodes remain sequential
within each run because episode N depends on every earlier script. The three runs
may execute concurrently.

```bash
cd /inspire/hdd/global_user/wangqiqi-CZXS25210124/ScriptPipeline_upstream_20260922
bash outline_history_baseline.sh prepare
bash outline_history_baseline.sh generate --workers 3 --execute-api
bash outline_history_baseline.sh status
bash outline_history_baseline.sh evaluate --workers 3 --execute-api
bash outline_history_baseline.sh report
```

All outputs are written under
`output/outline_direct_all_history_baseline_v1`. Re-running `generate` or
`evaluate` resumes completed work. Every accepted episode records the complete
history list, per-episode history hashes, prompt hash, exact prompt token count,
seed, output hash, and API usage in `request_metadata`.
