[![License](https://img.shields.io/badge/License-MIT-green.svg)](./LICENSE)
![Python](https://img.shields.io/badge/Python-TODO-blue.svg)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](./README.md#contributing)

# GELab-Zero

Local-first multimodal GUI agent infrastructure for Android devices, MCP orchestration, and cockpit-oriented hybrid GUI/API research.

> GELab-Zero puts three layers in one repository: a real-device Android GUI agent loop, an MCP service surface, and a virtual cockpit + HybridStress benchmark stack for studying API/GUI boundary failures.

[Technical Report](./report/Step-GUI_Technical_Report.pdf) | [简体中文](./README_CN.md) | [Idea Report](./IDEA_REPORT.md)

## Key Features

- OpenAI-compatible model backend. [`tools/ask_llm_v2.py`](./tools/ask_llm_v2.py) reads [`model_config.yaml`](./model_config.yaml) and can talk to local or remote endpoints that expose the ChatCompletion-style API.
- Real Android control loop. The agent captures screenshots, builds multimodal prompts, predicts structured actions, and executes them on-device through `adb` and the bundled `yadb` helper.
- MCP-ready service layer. [`mcp_server/detailed_gelab_mcp_server.py`](./mcp_server/detailed_gelab_mcp_server.py) exposes device discovery, task execution, and hybrid routing through MCP tools.
- Human-in-the-loop continuation. The execution loop supports `INFO` turns, `session_id` continuation, and `reply_from_client` handoff for tasks that need clarification or manual verification.
- Research-friendly cockpit stack. [`cockpit/`](./cockpit) provides a virtual IVI simulator with 7 subsystems, while [`hybridstress/`](./hybridstress) adds replay, fault injection, validators, and detector training for hybrid API/GUI evaluation.

## Architecture

### 1. Android GUI Agent Loop

```text
Task
  -> examples/* or MCP client
  -> copilot_agent_server/local_server.py
  -> copilot_tools/parser_0920_summary.py
  -> tools/ask_llm_v2.py
  -> structured action (CLICK / TYPE / WAIT / ...)
  -> copilot_front_end/pu_frontend_executor.py
  -> Android device via adb + yadb
  -> screenshot feedback loop
```

### 2. Hybrid Cockpit Path

```text
Task
  -> mcp_server/detailed_gelab_mcp_server.py
  -> CockpitRouter (API-first)
  -> cockpit/* tool or external API integration
  -> GUI fallback when no route matches or tool execution fails
  -> hybridstress/* replay + validation pipeline
```

## Quick Start

### Prerequisites

- Python: `[TODO: confirm and document the recommended Python version]`
- Android Platform Tools (`adb`)
- At least one Android device visible in `adb devices`, with developer options / USB debugging enabled
- A reachable model endpoint configured in [`model_config.yaml`](./model_config.yaml)
- Optional for cockpit benchmarking: `playwright` + Chromium

The repository already includes a `yadb` binary at the project root. On first run, [`copilot_front_end/mobile_action_helper.py`](./copilot_front_end/mobile_action_helper.py) will push it to `/data/local/tmp` if needed.

### Installation

```bash
git clone https://github.com/Haotian020527/gelab-zero.git
cd gelab-zero
pip install -r requirements.txt
```

Optional dependencies for the cockpit benchmark and detector pipeline:

```bash
pip install -r hybridstress/requirements.txt
pip install playwright
playwright install chromium
```

### Configure The Model Endpoint

[`model_config.yaml`](./model_config.yaml) already contains two providers:

```yaml
local:
  api_base: "http://localhost:11434/v1"
  api_key: "EMPTY"

stepfun:
  api_base: "https://api.stepfun.com/v1"
  api_key: "EMPTY"
```

Use `local` for a self-hosted OpenAI-compatible endpoint, or fill in a valid remote provider key before running examples.

### Usage / Demo

#### 1. Smoke-test the model API with a static screenshot

```bash
python examples/run_test_api.py --task "Open WeChat" --image images/test_api.png
```

This does not operate a real device. It only verifies that the model endpoint is reachable and returns a parsable action.

#### 2. Run the direct Android task loop

```bash
adb devices
python examples/run_single_task.py "Open WeChat"
```

[`examples/run_single_task.py`](./examples/run_single_task.py) uses the first connected device, captures screenshots, and executes the predicted action sequence directly.

#### 3. Run through MCP

Start the MCP server:

```bash
python mcp_server/detailed_gelab_mcp_server.py
```

Then run a task through the hybrid client:

```bash
python examples/run_hybrid_task.py "Open WeChat"
```

To inspect the MCP surface only:

```bash
python examples/run_task_via_mcp.py
```

#### 4. Launch the virtual cockpit and benchmark pipeline

Start the cockpit simulator:

```bash
python -m cockpit.app
```

Then open [http://localhost:8420](http://localhost:8420).

Run the cockpit sanity stage:

```bash
python -m hybridstress.run_benchmark --stage sanity --backend cockpit --output hybridstress_sanity
```

## Repository Structure

```text
.
|-- cockpit/                 # FastAPI virtual IVI simulator and frontend
|-- copilot_agent_client/    # Task loop orchestration and MCP-driven execution
|-- copilot_agent_server/    # Session management, logging, parser dispatch, model calls
|-- copilot_front_end/       # adb / yadb actions, screenshots, package mapping
|-- copilot_tools/           # Prompt protocol and action parsing
|-- examples/                # API smoke test, direct run, MCP hybrid run
|-- hybridstress/            # Boundary-failure benchmark, replay, detectors, recovery
|-- images/                  # README assets and demo media
|-- mcp_server/              # MCP tools, hybrid routing, cockpit integrations
|-- tools/                   # Model, prompt, image, and data utilities
|-- model_config.yaml        # Model endpoint configuration
|-- mcp_server_config.yaml   # Agent loop + MCP server configuration
\-- yadb                     # Bundled device-side input helper
```

## Contributing

PRs are welcome.

- Keep example commands reproducible and update the README when the entrypoint changes.
- If you modify the action protocol, update both the parser and the device executor.
- If you change cockpit APIs or hybrid routing, sync the related validators and task definitions.

## License

This project is released under the [MIT License](./LICENSE).
