[![License](https://img.shields.io/badge/License-MIT-green.svg)](./LICENSE)
![Python](https://img.shields.io/badge/Python-TODO-blue.svg)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](./README_CN.md#贡献指南)

# GELab-Zero

面向 Android 设备、MCP 编排与智能座舱混合 GUI/API 研究的本地优先多模态 GUI Agent 基础设施。

> GELab-Zero 并不是单一脚本仓库，而是把三层能力放在了一起：真实 Android 设备上的 GUI Agent 执行链、面向外部系统的 MCP 服务层，以及用于混合 API/GUI 决策研究的虚拟座舱与 HybridStress 基准。

[Technical Report](./report/Step-GUI_Technical_Report.pdf) | [English](./README.md) | [Idea Report](./IDEA_REPORT.md)

## 核心特性

- OpenAI 兼容模型后端。[`tools/ask_llm_v2.py`](./tools/ask_llm_v2.py) 通过 [`model_config.yaml`](./model_config.yaml) 读取模型配置，可对接本地或远端的 ChatCompletion 风格接口。
- 真实设备 GUI 执行链。仓库会采集截图、拼装多模态提示词、解析结构化动作，并通过 `adb` 与内置 `yadb` 在 Android 设备上执行。
- MCP 服务化入口。[`mcp_server/detailed_gelab_mcp_server.py`](./mcp_server/detailed_gelab_mcp_server.py) 暴露了设备发现、任务执行和混合路由能力，便于接入上层 Agent 或外部编排系统。
- 支持人机协同续跑。任务中出现 `INFO` 动作时，可以通过 `session_id` 和 `reply_from_client` 继续会话，适合处理澄清、验证码或人工确认场景。
- 面向研究的座舱栈。[`cockpit/`](./cockpit) 提供 7 个 IVI 子系统的虚拟座舱模拟器，[`hybridstress/`](./hybridstress) 提供故障注入、三分支 replay、验证器与检测器训练流程。

## 架构解析

### 1. Android GUI Agent 主链路

```text
任务文本
  -> examples/* 或 MCP 客户端
  -> copilot_agent_server/local_server.py
  -> copilot_tools/parser_0920_summary.py
  -> tools/ask_llm_v2.py
  -> 结构化动作（CLICK / TYPE / WAIT / ...）
  -> copilot_front_end/pu_frontend_executor.py
  -> 通过 adb + yadb 操作 Android 设备
  -> 截图回流形成闭环
```

### 2. 智能座舱混合路径

```text
任务文本
  -> mcp_server/detailed_gelab_mcp_server.py
  -> CockpitRouter（API-first）
  -> cockpit/* 工具或外部 API 集成
  -> 无法匹配或工具失败时回退到 GUI 执行
  -> hybridstress/* 做 replay、验证与统计分析
```

## 快速开始

### 环境依赖

- Python：`[TODO: 补充推荐 Python 版本]`
- Android Platform Tools（`adb`）
- 至少 1 台能在 `adb devices` 中看到的 Android 设备，并已开启开发者模式 / USB 调试
- 一个可访问的模型服务，并在 [`model_config.yaml`](./model_config.yaml) 中完成配置
- 如果要运行座舱模拟器与基准：`playwright` + Chromium

仓库根目录已经包含 `yadb` 二进制文件。首次运行时，[`copilot_front_end/mobile_action_helper.py`](./copilot_front_end/mobile_action_helper.py) 会在设备缺失该工具时自动推送到 `/data/local/tmp`。

### 安装步骤

```bash
git clone https://github.com/Haotian020527/gelab-zero.git
cd gelab-zero
pip install -r requirements.txt
```

如果要运行智能座舱基准与检测器训练，再安装可选依赖：

```bash
pip install -r hybridstress/requirements.txt
pip install playwright
playwright install chromium
```

### 配置模型服务

[`model_config.yaml`](./model_config.yaml) 当前已经提供两个 provider：

```yaml
local:
  api_base: "http://localhost:11434/v1"
  api_key: "EMPTY"

stepfun:
  api_base: "https://api.stepfun.com/v1"
  api_key: "EMPTY"
```

其中 `local` 适合对接本地或自托管的 OpenAI 兼容服务；如果使用远端 provider，请先补全对应 `api_key`。

### 运行示例

#### 1. 先做静态截图 API 冒烟测试

```bash
python examples/run_test_api.py --task "打开微信" --image images/test_api.png
```

这个脚本不会操作真实设备，只用一张静态截图验证模型接口是否可达、返回动作是否可被解析。

#### 2. 直接运行 Android 任务链路

```bash
adb devices
python examples/run_single_task.py "打开微信"
```

[`examples/run_single_task.py`](./examples/run_single_task.py) 会默认取第一台已连接设备，执行“截图 -> 预测动作 -> 落地动作”的完整闭环。

#### 3. 通过 MCP 运行

先启动 MCP 服务：

```bash
python mcp_server/detailed_gelab_mcp_server.py
```

再执行混合任务客户端：

```bash
python examples/run_hybrid_task.py "打开微信"
```

如果你只想查看 MCP 暴露了哪些工具：

```bash
python examples/run_task_via_mcp.py
```

#### 4. 启动虚拟座舱与 HybridStress

启动座舱模拟器：

```bash
python -m cockpit.app
```

然后访问 [http://localhost:8420](http://localhost:8420)。

运行座舱后端的 sanity 阶段：

```bash
python -m hybridstress.run_benchmark --stage sanity --backend cockpit --output hybridstress_sanity
```

## 项目结构

```text
.
|-- cockpit/                 # FastAPI 虚拟座舱、前端页面与 IVI 子系统
|-- copilot_agent_client/    # 任务循环编排与 MCP 驱动执行
|-- copilot_agent_server/    # 会话管理、日志记录、parser 分发、模型调用
|-- copilot_front_end/       # adb / yadb 动作执行、截图采集、包名映射
|-- copilot_tools/           # 动作协议与提示词解析
|-- examples/                # API 冒烟测试、直接执行、MCP 混合执行示例
|-- hybridstress/            # 边界失效基准、replay、检测器与恢复评估
|-- images/                  # README 素材与演示媒体
|-- mcp_server/              # MCP 服务、混合路由与座舱集成
|-- tools/                   # 模型、提示词、图像与数据处理工具
|-- model_config.yaml        # 模型服务配置
|-- mcp_server_config.yaml   # Agent Loop 与 MCP 服务配置
\-- yadb                     # 设备侧输入辅助工具
```

## 贡献指南

欢迎提交 Issue 和 PR。

- 如果入口脚本或命令发生变化，请同步更新 README 和 `examples/`。
- 如果修改动作协议，请同时检查 parser 与设备执行器是否仍然一致。
- 如果改动了 cockpit API 或混合路由逻辑，请同步更新相关 validator 与 task definition。

## 开源协议

本项目基于 [MIT License](./LICENSE) 开源。
