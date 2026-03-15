# Runtime Responsibility Boundary

更新时间：2026-03-15

## 目标

这份文档只回答三个问题：

- `RuntimeOrchestrator` 的职责到底是什么
- runtime / session / release / presentation 之间的方法归属应该怎么切
- 整理前后，每个包、文件应该持有哪些方法

这份文档不讨论方法实现，也不讨论具体重构步骤。

## 结论

`RuntimeOrchestrator` 不是“runtime 里的总控大类”，而是消息进入系统后的主路径编排器。

它应只负责：

- 入口守门：鉴权、去重、忽略无效消息、顶层异常边界
- 会话解析：为当前消息解析 session scope 与 session record
- 执行分流：决定进入命令分发还是 backend turn
- 执行协调接线：把 execution / turn / delivery / session / release 协作者接起来

它不应继续负责：

- 命令业务细节
- 帮助、面板、状态、会话列表等展示文本或 view-model
- Feishu reply route、card update target、fallback 发送策略
- systemd / 进程重启细节
- turn 输入整形与 streaming UI 细节

## 归属判断规则

先给出一条稳定判断标准，避免后续每加一个方法都重新争论。

### runtime

方法属于 runtime，当且仅当它主要在做下面四类事情之一：

- 决定一条消息现在走哪条主路径
- 维护 run / lock / cancel / follow-up 之类执行态
- 组织 backend、messenger、store、session、release 协作者之间的调用顺序
- 提供顶层异常边界和进程级控制

一句话说，runtime 负责“这条消息怎么被处理”。

### session

方法属于 session，当它主要在做下面事情：

- 定义 session scope、session key、thread alias 的语义
- 装载、浏览、恢复、切换、重置 session
- 处理 cwd、shortcut、session metadata 这些会话域状态
- 给 runtime 提供稳定的 session 数据结构和查询接口

一句话说，session 负责“这条消息落到哪个会话，以及这个会话当前是什么状态”。

### release

方法属于 release，当它主要回答：

- 当前 release channel 是什么
- 切换 channel 会产生什么 session / 事件结果
- main / develop 这种用户命令如何映射到 release 语义

一句话说，release 负责“会话使用哪条发布通道，以及切换后产生什么结果”。

### presentation

方法属于 presentation，只要它的主要产物是用户可见内容，而不是状态变更：

- 文本文案
- 卡片结构
- view-model
- 列表项 / meta / preview / usage / status 摘要

只要一个方法返回的核心价值是“给用户看”，它就不应留在 runtime / session / release 主域里。

## 命名判断

当前 `src/openrelay/runtime/commands.py` 更接近 `command_dispatcher.py`，不是 `router.py`。

原因：

- `router` 更强调“按名字把请求路由到 handler”
- 当前模块除了解析命令，还承担权限判断、业务动作分发、参数解释和部分回复入口协作
- 因此 `dispatcher` 比 `router` 更准确

## 整理前

### openrelay.runtime

#### `src/openrelay/runtime/orchestrator.py`

- `__init__`
- `shutdown`
- `_compose_session_key`
- `_thread_session_key_candidates`
- `_is_command_message`
- `_is_top_level_message`
- `_is_top_level_control_command`
- `build_session_key`
- `_remember_thread_session_alias`
- `_remember_outbound_aliases`
- `is_allowed_user`
- `is_admin`
- `_build_execution_key`
- `_load_session_for_message`
- `_resolve_stop_execution_key`
- `_message_summary_text`
- `_build_backend_prompt`
- `dispatch_message`
- `_handle_message_serialized`
- `_handle_single_serialized_input`
- `_run_backend_turn`
- `_handle_command`
- `_handle_stop`
- `_cancel_active_run_for_session`
- `_build_card_action_context`
- `_build_turn_runtime_context`
- `_send_help`
- `_reply_final`
- `_reply`
- `_reply_command_fallback`
- `available_backend_names`
- `_send_text_reply`
- `_is_stop_command`
- `_should_bypass_active_run`
- `_schedule_restart`
- `_restart_process`
- `_restart_systemd_service`

#### `src/openrelay/runtime/commands.py`

- `RuntimeCommandRouter.handle`
- `_handle_resume`
- `_is_top_level_p2p_command`
- `_is_card_action_message`
- `_can_use_top_level_session_command`
- `_top_level_thread_scope_key`
- `_parse_resume_command_args`
- `_parse_panel_command_args`
- `_parse_paging_command_args`
- `_normalize_panel_view`
- `_parse_positive_int`
- `_handle_release_switch`
- `_handle_cwd`
- `_handle_backend`
- `_handle_shortcut`
- `_parse_shortcut_add`
- `_build_status_text`

#### `src/openrelay/runtime/execution.py`

- `is_locked`
- `lock_for`
- `active_run`
- `start_run`
- `finish_run`
- `try_handle_live_input`
- `enqueue_pending_input`
- `dequeue_pending_input`
- `queued_follow_up_count`

#### `src/openrelay/runtime/turn.py`

- `BackendTurnSession.run`
- `prepare`
- `persist_native_thread_id`
- `cancel`
- `build_interaction_controller`
- `activate_run`
- `build_backend_context`
- `on_partial_text`
- `on_progress`
- `reply_target_message_id`
- `save_reply`
- `reply_final`
- `finalize`
- `_start_typing`
- `_start_streaming_if_needed`
- `_stop_spinner_task`
- `_request_streaming_update`
- `_update_streaming`
- `_spinner_loop`

#### `src/openrelay/runtime/replying.py`

- `default_route`
- `command_route`
- `command_reply_target`
- `command_card_update_target`
- `should_force_new_message_for_command`
- `should_force_new_message_for_command_card`
- `build_card_action_context`
- `root_id_for_message`
- `is_card_action_message`
- `is_top_level_p2p_command`

#### `src/openrelay/runtime/panel_service.py`

- `send_panel`
- `send_session_list`
- `_build_panel_base_info`
- `_build_panel_command_entries`
- `_build_panel_status_entries`
- `_build_panel_home_text`
- `_build_panel_sessions_text`
- `_build_panel_directories_text`
- `_build_panel_commands_text`
- `_build_panel_status_text`

#### `src/openrelay/runtime/restart.py`

- controller / schedule 状态管理方法
- 进程重启主流程方法仍部分留在 `orchestrator.py`

### openrelay.session

#### `src/openrelay/session/scope/resolver.py`

- `compose_key`
- `thread_candidates`
- `build_session_key`
- `remember_inbound_aliases`
- `remember_outbound_aliases`
- `is_command_message`
- `is_top_level_message`
- `is_top_level_control_command`
- `is_card_action_message`
- `root_id_for_message`
- `_thread_ids`

#### `src/openrelay/session/lifecycle.py`

- `load_for_message`
- `_load_control_session`
- `_find_visible_control_session`
- `_is_placeholder_control_session`

#### `src/openrelay/session/browser.py`

- `list_entries`
- `list_page`
- `normalize_sort_mode`
- `resume`
- `resolve_target`
- `find_entry`
- `find_local_session`
- `_local_entry`
- `_sort_entries`

#### `src/openrelay/session/mutations.py`

- `create_named_session`
- `clear_context`
- `switch_model`
- `switch_sandbox`
- `switch_backend`
- `switch_cwd`
- `switch_release_channel`
- `reset_scope`
- `save_directory_shortcut`
- `remove_directory_shortcut`

#### `src/openrelay/session/workspace.py`

- `format_cwd`
- `resolve_cwd`

#### `src/openrelay/session/shortcuts.py`

- `build_directory_shortcut_entries`
- `list_directory_shortcuts`
- `resolve_directory_shortcut`
- `_resolve_directory_shortcut_target`

#### `src/openrelay/session/ux.py`

- `shorten`
- `effective_model`
- `label_session_if_needed`
- `format_cwd`
- `build_session_title`
- `build_session_preview`
- `build_session_meta`
- `build_session_display_entries`
- `format_session_list`
- `format_session_list_page`
- `_format_session_displays`
- `format_resume_success`
- `build_context_preview`
- `build_context_lines`
- `format_context_usage`
- `build_usage_lines`

### openrelay.release

#### `src/openrelay/release/service.py`

- `switch_channel`

## 整理后

目标不是把方法平均分给更多文件，而是把主路径压回稳定边界：

- runtime 只保留编排、执行态和 delivery 协调
- session 只保留会话域状态与规则
- release 只保留发布通道切换语义
- presentation 统一承接所有用户可见文本、卡片与 view-model

### openrelay.runtime

#### `src/openrelay/runtime/orchestrator.py`

应只保留顶层消息编排方法：

- `__init__`
- `shutdown`
- `is_allowed_user`
- `is_admin`
- `_build_execution_key`
- `_resolve_stop_execution_key`
- `_message_summary_text`
- `_build_backend_prompt`
- `dispatch_message`
- `_handle_message_serialized`
- `_handle_single_serialized_input`
- `_run_backend_turn`
- `_handle_command`
- `_handle_stop`
- `_cancel_active_run_for_session`
- `_build_turn_runtime_context`
- `_reply`
- `_reply_final`
- `_reply_command_fallback`
- `_send_text_reply`
- `available_backend_names`
- `_is_stop_command`
- `_should_bypass_active_run`
- `_schedule_restart`

不应继续保留下面这些“只是替下游转发”的包装方法：

- `_compose_session_key`
- `_thread_session_key_candidates`
- `_is_command_message`
- `_is_top_level_message`
- `_is_top_level_control_command`
- `build_session_key`
- `_remember_thread_session_alias`
- `_remember_outbound_aliases`
- `_load_session_for_message`
- `_build_card_action_context`
- `_send_help`
- `_restart_process`
- `_restart_systemd_service`

这些方法的问题不是“代码行数多”，而是会继续制造一个错觉：好像所有能力都应该先挂回 orchestrator，再转发到真正协作者。

#### `src/openrelay/runtime/commands.py`

这个文件的目标职责是“命令分发器”，不是“命令全家桶”。它应保留：

- `RuntimeCommandDispatcher.handle`
- `_handle_resume`
- `_handle_release_switch`
- `_handle_cwd`
- `_handle_backend`
- `_handle_shortcut`
- `_parse_resume_command_args`
- `_parse_panel_command_args`
- `_parse_paging_command_args`
- `_normalize_panel_view`
- `_parse_positive_int`
- `_parse_shortcut_add`

它不应继续持有：

- `_is_top_level_p2p_command`
- `_is_card_action_message`
- `_can_use_top_level_session_command`
- `_top_level_thread_scope_key`
- `_build_status_text`

前四个属于 session scope / reply policy 规则，最后一个属于 presentation。

也就是说，dispatcher 可以决定“调用哪个服务”，但不应自己定义 scope 语义，也不应直接拼状态文案。

#### `src/openrelay/runtime/execution.py`

这个文件边界已经相对稳定，应继续只保留执行态协调：

- `is_locked`
- `lock_for`
- `active_run`
- `start_run`
- `finish_run`
- `try_handle_live_input`
- `enqueue_pending_input`
- `dequeue_pending_input`
- `queued_follow_up_count`

这里不应混入命令判断、session 解析或任何用户可见文案。

#### `src/openrelay/runtime/turn.py`

这个文件应只保留 turn 生命周期与 runtime-side 交互协调：

- `BackendTurnSession.run`
- `prepare`
- `persist_native_thread_id`
- `cancel`
- `build_interaction_controller`
- `activate_run`
- `build_backend_context`
- `on_partial_text`
- `on_progress`
- `reply_target_message_id`
- `save_reply`
- `reply_final`
- `finalize`
- `_start_typing`
- `_start_streaming_if_needed`
- `_stop_spinner_task`
- `_request_streaming_update`
- `_update_streaming`
- `_spinner_loop`

但这里有一条额外约束：

- turn 可以驱动 streaming 更新
- turn 不应自己定义 streaming card 的文案结构、markdown 语义和展示组件

也就是说，`turn.py` 负责“什么时候更新”，presentation 负责“更新成什么样”。

#### `src/openrelay/runtime/replying.py`

这个文件应保留渠道发送策略与 reply target 规则：

- `default_route`
- `command_route`
- `command_reply_target`
- `command_card_update_target`
- `should_force_new_message_for_command`
- `should_force_new_message_for_command_card`
- `build_card_action_context`
- `root_id_for_message`
- `is_card_action_message`
- `is_top_level_p2p_command`

这里解决的是“回到哪条消息、发新消息还是原地更新”，不是“内容长什么样”。

#### `src/openrelay/runtime/panel_service.py`

这个文件可以保留，但只能作为发送协调器：

- `send_panel`
- `send_session_list`

它不应继续持有：

- `_build_panel_base_info`
- `_build_panel_command_entries`
- `_build_panel_status_entries`
- `_build_panel_home_text`
- `_build_panel_sessions_text`
- `_build_panel_directories_text`
- `_build_panel_commands_text`
- `_build_panel_status_text`

这些都是 presentation 逻辑，不是 runtime 逻辑。

#### `src/openrelay/runtime/restart.py`

这个文件应完整承接重启控制：

- `get_systemd_service_unit`
- `is_systemd_service_process`
- `RuntimeRestartController.schedule_restart`
- `RuntimeRestartController.mark_failed`
- 以及原来还留在 orchestrator 里的进程重启主流程

整理完成后，orchestrator 只允许“发起重启”，不允许自己持有进程控制细节。

#### `src/openrelay/runtime/interactions/*`

这里应继续保留“运行时交互协议”本身：

- 交互状态模型
- 请求 / 应答的 runtime 协调
- approval / user input 的等待与恢复

但卡片 payload 的拼装、按钮文案和解释文本，应转交给 presentation。

### openrelay.session

#### `src/openrelay/session/scope/resolver.py`

这个文件保留全部 session scope 语义：

- `compose_key`
- `thread_candidates`
- `build_session_key`
- `remember_inbound_aliases`
- `remember_outbound_aliases`
- `is_command_message`
- `is_top_level_message`
- `is_top_level_control_command`
- `_thread_ids`

另外，下面几个方法虽然今天放在这里也合理，但从长期看应只由一个边界统一暴露：

- `is_card_action_message`
- `root_id_for_message`

如果 runtime.replying 已经成为消息渠道规则的唯一入口，那么这两个方法不应在 session 和 runtime 里各自再长一份语义。

#### `src/openrelay/session/lifecycle.py`

保留全部 session 装载与占位控制：

- `load_for_message`
- `_load_control_session`
- `_find_visible_control_session`
- `_is_placeholder_control_session`

这里回答的是“当前消息拿到哪个 SessionRecord”，不涉及展示。

#### `src/openrelay/session/browser.py`

保留会话浏览与恢复：

- `list_entries`
- `list_page`
- `normalize_sort_mode`
- `resume`
- `resolve_target`
- `find_entry`
- `find_local_session`
- `_local_entry`
- `_sort_entries`

它应产出稳定数据结构，如 `SessionListEntry` / `SessionListPage` / `SessionResumeResult`，但不负责把这些结构格式化成文本或卡片。

#### `src/openrelay/session/mutations.py`

应保留纯 session 变更动作：

- `create_named_session`
- `clear_context`
- `switch_model`
- `switch_sandbox`
- `switch_backend`
- `switch_cwd`
- `reset_scope`
- `save_directory_shortcut`
- `remove_directory_shortcut`

不应继续保留：

- `switch_release_channel`

release channel 切换不是一般性的 session mutation，而是 release 域动作。它可以产生“新 session + 事件记录 + 命令反馈所需结果”，因此应由 `openrelay.release` 统一拥有。

#### `src/openrelay/session/workspace.py`

保留 workspace 规则：

- `resolve_cwd`
- `format_cwd`

这里虽然会输出字符串，但它输出的是领域规则的标准表达，不是用户界面文案，因此仍属于 session。

#### `src/openrelay/session/shortcuts.py`

保留 shortcut 规则和解析：

- `list_directory_shortcuts`
- `resolve_directory_shortcut`
- `_resolve_directory_shortcut_target`

`build_directory_shortcut_entries` 不应继续留在这里，因为它已经是面向 panel / help 的展示入口数据，应转移到 presentation。

#### `src/openrelay/session/ux.py`

这个文件是当前最不稳定的边界。

整理后，它不应继续存在为一个大而全的 `SessionUX` 门面。当前方法应拆成两类：

第一类，仍然和 session 域强绑定、可保留为较薄服务或被下游直接替代：

- `effective_model`
- `label_session_if_needed`
- `shorten`

第二类，全部迁到 presentation：

- `build_session_title`
- `build_session_preview`
- `build_session_meta`
- `build_session_display_entries`
- `format_session_list`
- `format_session_list_page`
- `_format_session_displays`
- `format_resume_success`
- `build_context_preview`
- `build_context_lines`
- `format_context_usage`
- `build_usage_lines`

原因很简单：这些方法的核心产物是用户可见文本，不是 session 状态。

#### `src/openrelay/session/list_card.py`

这个文件也不应留在 session 包里。

- `build_resume_list_command`
- `build_session_list_card`
- `_session_text`

它们本质都是 presentation，而不是 session。

### openrelay.release

#### `src/openrelay/release/service.py`

release 包应只保留 release 语义和结果对象：

- `ReleaseSwitchResult`
- `ReleaseCommandService.switch_channel`

它需要回答：

- 目标 channel 是什么
- 是否真的发生切换
- 是否需要新 session
- 是否需要记录 release event
- 上层 presentation 需要哪些结构化结果

release 服务可以依赖 session mutation/store，但 session 不应反向持有 release 语义。

### openrelay.presentation

`presentation` 是这份文档新增的目标边界。它不是“各种 formatter 的杂物间”，而是统一承接用户可见输出。

#### `src/openrelay/presentation/help.py`

承接当前 `runtime/help.py` 的职责：

- `build_text`
- `build_card`
- `describe_session_phase`
- `build_now_summary`
- `build_context_note`
- `context_usage_ratio`
- `build_priority_actions`
- `build_prompt_examples`
- `build_command_guide`
- `build_command_button_groups`

#### `src/openrelay/presentation/panel.py`

承接当前 `runtime/panel.py` 和 `runtime/panel_service.py` 里的 view-model / card 构造：

- `build_panel_card`
- `_build_home_card`
- `_build_sessions_card`
- `_build_directories_card`
- `_build_commands_card`
- `_build_status_card`
- `_build_panel_base_info`
- `_build_panel_command_entries`
- `_build_panel_status_entries`
- `_build_panel_home_text`
- `_build_panel_sessions_text`
- `_build_panel_directories_text`
- `_build_panel_commands_text`
- `_build_panel_status_text`

#### `src/openrelay/presentation/sessions.py`

承接当前 `session/ux.py` 与 `session/list_card.py` 中面向用户的会话展示：

- `build_session_title`
- `build_session_preview`
- `build_session_meta`
- `build_session_display_entries`
- `format_session_list`
- `format_session_list_page`
- `format_resume_success`
- `build_context_preview`
- `build_context_lines`
- `format_context_usage`
- `build_usage_lines`
- `build_resume_list_command`
- `build_session_list_card`

#### `src/openrelay/presentation/status.py`

承接当前 `RuntimeCommandDispatcher._build_status_text`。

`/status`、`/usage` 这类命令的状态文案不应继续藏在命令分发器内部。

#### `src/openrelay/presentation/reply.py`

承接当前 `runtime/rendering.py` 与 `runtime/live.py` 的展示逻辑：

- reply markdown 渲染
- live status markdown / sections
- reasoning / tool / file change / progress 的展示映射
- final reply card 的构造

runtime.turn 只负责在合适时机调用这里，不再拥有展示语义本身。

#### `src/openrelay/presentation/interactions.py`

承接当前 `runtime/interactions/controller.py` 中与用户界面直接相关的部分：

- interaction card payload
- resolved card payload
- actions 文案与布局
- approval / question 的展示文本

这样 `RunInteractionController` 可以回到“等待、恢复、提交结果”的运行时角色。

## `RuntimeOrchestrator` 的最终边界

整理完成后，`RuntimeOrchestrator` 应满足下面四条约束：

- 它可以知道有哪些协作者，但不重复定义它们的内部语义。
- 它可以决定先调谁后调谁，但不自己生产大块展示内容。
- 它可以维护执行态，但不自己持有 session / release / presentation 的领域规则。
- 它可以保留少量粘合型 helper，但不能把下游服务重新包一层再暴露成自己的“私有能力库”。

如果一个新方法加进来后，回答的是“用户看见什么”“session 怎么切”“release 怎么切”“reply route 怎么选”，那它大概率就不该进 `RuntimeOrchestrator`。

## 文件收敛结果

从最终结构看，应该收敛为下面这组稳定角色：

- `runtime/orchestrator.py`：消息主路径编排器
- `runtime/commands.py`：命令分发器
- `runtime/execution.py`：执行态协调器
- `runtime/turn.py`：单次 backend turn 生命周期
- `runtime/replying.py`：reply route 与发送目标策略
- `runtime/restart.py`：进程重启控制
- `runtime/interactions/*`：运行时交互协议与等待恢复
- `session/scope/resolver.py`：session scope 语义
- `session/lifecycle.py`：session 装载策略
- `session/browser.py`：会话查询与恢复
- `session/mutations.py`：会话状态变更
- `session/workspace.py`：cwd / workspace 规则
- `session/shortcuts.py`：shortcut 规则
- `release/service.py`：release 切换语义
- `presentation/help.py`：帮助文案与帮助卡片
- `presentation/panel.py`：panel 文本、view-model、卡片
- `presentation/sessions.py`：会话列表、resume、usage、context 展示
- `presentation/status.py`：状态文案
- `presentation/reply.py`：reply / streaming / live progress 展示
- `presentation/interactions.py`：交互卡片展示

## 取舍

这份边界设计有两个刻意取舍：

- 不为了“看起来统一”把一切都塞进 presentation。像 `format_cwd` 这种仍然是 session 规则，不因为它返回字符串就被误判成展示层。
- 不为了“入口纯净”把所有粘合代码都拆到无数小类。runtime 仍然允许保留必要的 orchestration helper，但只限于主路径协调。

换句话说，这不是一次“平均拆文件”，而是一次“把每个方法放回它真正回答的问题里”。
