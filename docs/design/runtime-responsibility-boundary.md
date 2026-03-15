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

### openrelay.runtime

#### `src/openrelay/runtime/orchestrator.py`

只保留入口编排方法：

- `__init__`
- `shutdown`
- `dispatch_message`
- `_handle_message_serialized`
- `_handle_single_serialized_input`
- `_dispatch_command`
- `_dispatch_turn`
- `_resolve_execution_context`
- `is_allowed_user`
- `is_admin`

不再保留：

- reply / help / panel / session-list 发送方法
- restart 细节方法
- session scope 的转发型 helper
- turn 输入整形方法
- active-run bypass 策略方法

#### `src/openrelay/runtime/command_dispatcher.py`

保留 parse + dispatch：

- `handle`
- `_dispatch_builtin_command`
- `_dispatch_session_command`
- `_dispatch_workspace_command`
- `_dispatch_release_command`
- `_dispatch_runtime_command`
- `_parse_resume_args`
- `_parse_panel_args`
- `_parse_paging_args`
- `_parse_shortcut_add`
- `_parse_positive_int`

不再保留：

- 长文本拼装方法
- 具体业务动作实现方法
- 展示 fallback 文本方法

#### `src/openrelay/runtime/execution.py`

保留执行协调：

- `is_locked`
- `lock_for`
- `active_run`
- `start_run`
- `finish_run`
- `try_handle_live_input`
- `enqueue_pending_input`
- `dequeue_pending_input`
- `queued_follow_up_count`
- `should_bypass_active_run`
- `resolve_stop_target`

#### `src/openrelay/runtime/turn.py`

只保留单次 turn 生命周期：

- `run`
- `prepare`
- `persist_native_thread_id`
- `cancel`
- `activate_run`
- `build_backend_context`
- `save_reply`
- `finalize`

#### `src/openrelay/runtime/turn_interaction.py`

负责 turn 级交互桥接：

- `build_interaction_controller`
- `reply_target_message_id`

#### `src/openrelay/runtime/turn_streaming.py`

负责 streaming / typing / live progress：

- `on_partial_text`
- `on_progress`
- `reply_final`
- `_start_typing`
- `_start_streaming_if_needed`
- `_stop_spinner_task`
- `_request_streaming_update`
- `_update_streaming`
- `_spinner_loop`

#### `src/openrelay/runtime/reply_policy.py`

只负责发送策略计算：

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

#### `src/openrelay/runtime/delivery.py`

负责文本 / 卡片发送与 fallback：

- `reply_text`
- `reply_command_text`
- `reply_final`
- `send_help_card`
- `send_panel_card`
- `send_session_list_card`
- `send_text`
- `remember_outbound_aliases`

#### `src/openrelay/runtime/restart.py`

完整承接 restart：

- `schedule_restart`
- `restart_process`
- `restart_systemd_service`
- `mark_failed`
- `get_systemd_service_unit`
- `is_systemd_service_process`

### openrelay.runtime.presentation

#### `src/openrelay/runtime/presentation/help.py`

- `build_text`
- `build_card`

#### `src/openrelay/runtime/presentation/panel_presenter.py`

- `build_panel_home_model`
- `build_panel_sessions_model`
- `build_panel_directories_model`
- `build_panel_commands_model`
- `build_panel_status_model`
- `build_panel_home_text`
- `build_panel_sessions_text`
- `build_panel_directories_text`
- `build_panel_commands_text`
- `build_panel_status_text`

#### `src/openrelay/runtime/presentation/status_presenter.py`

- `build_status_text`
- `build_usage_text`

### openrelay.session

#### `src/openrelay/session/scope/resolver.py`

保留不变：

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

#### `src/openrelay/session/lifecycle.py`

保留不变：

- `load_for_message`
- `_load_control_session`
- `_find_visible_control_session`
- `_is_placeholder_control_session`

#### `src/openrelay/session/browser.py`

保留查询 / 恢复判定：

- `list_entries`
- `list_page`
- `normalize_sort_mode`
- `resume`
- `resolve_target`
- `find_entry`
- `find_local_session`

#### `src/openrelay/session/mutations.py`

保留 session 状态变更：

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

保留不变：

- `format_cwd`
- `resolve_cwd`

#### `src/openrelay/session/shortcuts.py`

保留 shortcut 规则：

- `build_directory_shortcut_entries`
- `list_directory_shortcuts`
- `resolve_directory_shortcut`

#### `src/openrelay/session/presentation.py`

保留纯展示方法：

- `shorten`
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

#### `src/openrelay/session/defaults.py`

保留 session 默认值与首轮 label 逻辑：

- `effective_model`
- `label_session_if_needed`

### openrelay.release

#### `src/openrelay/release/service.py`

保留 release 业务动作：

- `switch_channel`

#### `src/openrelay/release/presentation.py`

保留 release 切换展示：

- `build_switch_success_text`
- `build_switch_failure_text`

## 迁移映射

### 从 `runtime.orchestrator` 移出

- `_message_summary_text` -> `runtime.turn` 或 `runtime.turn_request`
- `_build_backend_prompt` -> `runtime.turn` 或 `runtime.turn_request`
- `_send_help` -> `runtime.delivery`
- `_reply` -> `runtime.delivery`
- `_reply_final` -> `runtime.delivery`
- `_send_text_reply` -> `runtime.delivery`
- `_should_bypass_active_run` -> `runtime.execution`
- `_schedule_restart` -> `runtime.restart`
- `_restart_process` -> `runtime.restart`
- `_restart_systemd_service` -> `runtime.restart`
- `_compose_session_key` / `_thread_session_key_candidates` / `_is_command_message` / `_is_top_level_message` / `_is_top_level_control_command` / `_remember_thread_session_alias` / `_remember_outbound_aliases` -> 直接由 `session.scope.resolver` 提供，不再保留 orchestrator 转发

### 从 `runtime.commands` 移出

- `_handle_release_switch` -> `release.service` + `release.presentation`
- `_handle_cwd` -> session 命令 handler
- `_handle_backend` -> session 命令 handler
- `_handle_shortcut` -> session / shortcuts 命令 handler
- `_build_status_text` -> `runtime.presentation.status_presenter`
- `_handle_resume` 中的展示文本 -> `session.presentation` 或 `runtime.presentation`

### 从 `runtime.turn` 移出

- `build_interaction_controller` -> `runtime.turn_interaction`
- `reply_target_message_id` -> `runtime.turn_interaction`
- `on_partial_text` / `on_progress` / `reply_final` / `_start_typing` / `_start_streaming_if_needed` / `_stop_spinner_task` / `_request_streaming_update` / `_update_streaming` / `_spinner_loop` -> `runtime.turn_streaming`

### 从 `runtime.panel_service` 移出

- `_build_panel_base_info`
- `_build_panel_command_entries`
- `_build_panel_status_entries`
- `_build_panel_home_text`
- `_build_panel_sessions_text`
- `_build_panel_directories_text`
- `_build_panel_commands_text`
- `_build_panel_status_text`

这些方法都应收敛到 `runtime.presentation.panel_presenter`

## 最终定义

`RuntimeOrchestrator` 的职责不是“做所有 runtime 相关的事”，而是：

- 决定当前输入属于哪个 session
- 决定当前输入该走哪个执行路径
- 决定冲突输入如何排队、取消或并行绕过
- 把执行结果交给专门的 delivery 层发送

换句话说，它是主路径编排器，不是业务容器，也不是展示容器。
