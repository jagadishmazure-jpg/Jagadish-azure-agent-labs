# Disaster signal fusion

Seismic waveforms, SAR satellite tiles, weather observations and ground displacement (GNSS uplift, tide gauge)
are fused into a per-region risk score for **flood, quake and tsunami**. Three analysis agents run in parallel,
a historical-pattern agent adds analog events, and a Bayesian coordinator combines everything. Foundry (mocked)
writes the situation summary, and a duty officer decides. **The system never sends a public alert**: there is
no tool for it, the writer's deny-list blocks `*alert*` / `*broadcast*` / `*siren*`, and an eval checks it.
All data is synthetic and all services are offline stand-ins (see the [root README](../../README.md#honest-note-on-mocks)).

## Flow

```mermaid
flowchart LR
  EH[(Event Hubs stand-in<br/>raw readings)] --> IW[Ingest-watch<br/>Functions-style QC handlers<br/>ADLS raw / curated stand-in]
  IW --> SA[Seismic Analysis<br/>time-series onset picker]
  IW --> SM[Satellite Monitoring<br/>SAR vision: ground displacement]
  IW --> WC[Weather Correlation<br/>rainfall + soil → flood]
  SA --> J[Join]
  SM --> J
  WC --> J
  J --> HP[Historical Pattern<br/>RAG over the event archive]
  HP --> PC[Prediction Coordinator<br/>Bayesian log-odds fusion]
  PC --> RISK[Risk + geospatial exposure<br/>Azure Maps stand-in]
  RISK --> SUM[Situation summary<br/>Foundry, summary only]
  SUM --> H{{Alert decision<br/>duty officer HITL}}
  H --> OUT([decision record<br/>public_alert_sent = false])
```

## Agents

| Agent | Signals | Method |
|---|---|---|
| Seismic Analysis | seismogram, GNSS / tide displacement | `TinyRecurrentPicker`: a hand-weighted recurrent cell (`h_t = tanh(a·h_{t-1} + b·abs(x_t) + c)`) for onset and coda length. It is a deterministic stand-in, not a trained network |
| Satellite Monitoring | SAR interferogram tiles | Vision stand-in: median phase → ground displacement (mm), coherence as quality. If the tile is missing, it falls back to a neighbouring region |
| Weather Correlation | 24 h rain, rain rate, soil moisture | rainfall → flood likelihood ratio, scaled by a runoff factor for wet ground |
| Historical Pattern | event archive | hybrid retrieval (AI Search stand-in) of analog events in the region → base rates |
| Prediction Coordinator | all findings | posterior log-odds = prior + Σ quality-weight × LLR + small history term. Low-quality or missing sources fall back to the prior and widen the uncertainty |

The three analysis agents are MAF parallel branches (fan-out / fan-in). Ingest-watch drops stale readings and
records why. QC handlers in `functions.py` are shaped like Azure Functions triggers and reject malformed payloads.

## Outputs

* **Risk score:** 0–100 per hazard with a level (low / elevated / high / severe). It is the posterior multiplied by a geospatial exposure factor.
* **Evidence:** per-source contributions, weights, fallbacks and uncertainty for every hazard.
* **Affected facilities** found by point-in-polygon and distance (hospitals, schools, dams, hazmat sites, shelters), plus **decision-support options** for the duty officer.
* **Situation summary** (Foundry, mocked): validated so it only cites sources the fusion used and records that were retrieved, and it contains no forbidden alert phrasing.
* **Alert decision request** (HITL). The officer's decision is recorded. A public alert is never sent automatically.

## Evaluation (`evals/run_eval.py`)

| Metric | Question | Threshold | Current |
|---|---|---|---|
| signal_usage_rate | does every required source actually move the hazard? (5 gold cases) | = 1.0 | 1.0 |
| rain_sensitivity | does +100 mm of rain raise flood evidence and never lower the posterior? | = 1.0 | 1.0 |
| replay_hazard_accuracy | historical replay (8 held-out events): dominant hazard | ≥ 0.85 | 1.0 |
| replay_level_within_one | replay: risk level within one band | = 1.0 | 1.0 |
| fallback_flagged | dead-sensor events record a fallback | = 1.0 | 1.0 |
| no_public_alert | approved runs never send a public alert | = 1.0 | 1.0 |

## Engineering layers

| Layer | Status | Where |
|---|---|---|
| Business understanding | implemented | decision support for a duty officer; public alerting stays with the authorised person |
| Data understanding | implemented | raw payload QC, stale / neighbour handling, quality weights (`functions.py`, `workflow.IngestWatch`) |
| Knowledge engineering | implemented | historical archive indexed for analog retrieval, facility GeoJSON, hazard playbook |
| Model engineering | implemented | onset picker, SAR displacement, rainfall LLR, Bayesian fusion (`agents.py`) |
| Context engineering | implemented | region context from the Maps stand-in (neighbours, exposure, coastal flag) shapes every agent |
| Semantic engineering | implemented | Pydantic `RawEvent`, `CuratedSignal`, `Finding`, `SituationSummary`, `AlertReview` |
| Agent engineering | implemented | three parallel analysis agents, historical agent, coordinator on MAF fan-out / fan-in |
| Loop engineering | not in scope | one pass per assessment; no re-query loop |
| Evaluation engineering | implemented | signal usage, rain sensitivity, historical replay, fallbacks, no-public-alert |
| Harness engineering | implemented | deny-listed alert tools, schema validation, retries, step budget, summary citation / phrase check |
| Infrastructure engineering | implemented (compile-only) | `infra/main.bicep`: Event Hubs, ADLS Gen2, Function App, Maps, AI Search, Foundry, App Insights |
| Continual learning | not in scope | the archive is read-only here; see the wind-turbine lab |

## Domains you learn

Geospatial reasoning · remote sensing · time-series signals · risk prediction · multi-signal fusion · emergency decision support

## Transferable domains

Disaster management · smart cities · climate tech · infrastructure · energy · public safety

## Run

```bash
pytest -q labs/disaster-signal-fusion
python labs/disaster-signal-fusion/evals/run_eval.py --out evals-out
```

## Limitations

* Every signal is synthetic. The picker, SAR analysis and likelihood ratios are hand-set to be explainable, not calibrated against real catalogs.
* The risk score supports a person's decision. It is not a warning product and has no authority to warn anyone.
