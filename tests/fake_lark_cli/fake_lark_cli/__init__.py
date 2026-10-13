"""mock lark-cli：实验室的假命令行，读同一批夹具，按真 lark-cli 的信封回话。

YAML 里不出现任何 lark-cli 命令，命令只活在真实能力里；真实能力走子进程
调 `lark-cli`——本包把 PATH 里的真 lark-cli 遮蔽掉，让真实能力代码一行不改
就能离线自测。设计见 tests/fake_lark_cli/README.md。
"""
