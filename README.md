# 量潮飞书适配实验室

飞书适配的实验原型：验证信息架构与接口假设。

## 现状：骨架

与平台仓 `apps/qtcloud-feishu`（qtcloud-feishu CLI）功能重复的部分已删除，只保留骨架，方便后续
继续迭代。功能正本在平台仓 `src/cli/`：

| 本仓原内容 | 正本（`apps/qtcloud-feishu/src/cli/`） |
| :-- | :-- |
| `src/feishu/`：基础单元 + 串联器 | `src/`（`resources/`、`engine.rs`、`flow.rs`） |
| `examples/qtrecurit/`：流程、定义、执行器 | `examples/`（`qtrecurit.rs`、`pipelines/`） |
| `tests/`：假 lark-cli、夹具、冒烟 | `tests/` |
| `docs/`：能力清单、场景设计 | `README.md`、`docs/index.md` |

## 目录

| 路径 | 是什么 |
| :-- | :-- |
| `src/feishu/` | 包骨架：后续实验从这里重建 |
| `requirements.txt` | 依赖（pyyaml） |

## 许可

[Apache License 2.0](LICENSE)
