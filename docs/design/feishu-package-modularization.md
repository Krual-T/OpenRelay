# Feishu Package Modularization

更新时间：2026-03-14

## 背景

`src/openrelay/feishu.py` 同时承担了三类职责：

- webhook / 卡片动作解析
- 飞书消息发送与资源下载
- 事件分发与入站媒体解析

这些职责共享少量底层工具，但生命周期和关注点并不相同。继续把新逻辑塞进单文件，只会让边界越来越模糊。

## 目标

本轮把飞书接入层收敛为包结构，而不是继续维持“一体化工具箱”：

- `openrelay.feishu.parsing` 负责 webhook 与消息解析
- `openrelay.feishu.messenger` 负责消息发送、更新、资源下载
- `openrelay.feishu.dispatcher` 负责 SDK handler 与调度
- `openrelay.feishu.common` 只保留少量共享底层工具

`openrelay.feishu` 包本身只作为对外稳定入口，负责重导出当前公开接口。

## 取舍

- 不引入新的适配器抽象层，避免把简单拆分变成过度设计。
- 不改变 `openrelay.feishu` 的对外导入方式，先保证调用方和测试无需跟着大规模迁移。
- 不在这一轮处理 `feishu_ws.py`，因为它的职责边界已经相对独立。

## 预期收益

- 降低单文件体量，后续解析与发送逻辑可以独立演进。
- 让 webhook 解析、消息发送、事件分发各自拥有稳定落点。
- 去掉旧的“一份文件承载整个飞书层”的组织方式，为后续继续清理旧逻辑提供基础。
