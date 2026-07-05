# 代码审核清单

## ✅ 提交信息
- **提交哈希**: 81f3774
- **分支**: feat/update-download-install
- **基于**: afb7be3 (feat(bili): 剪贴板嗅探只匹配视频链接)

## 📊 变更统计
- **新增文件**: 3 个
- **修改文件**: 6 个
- **总行数变更**: +868 / -27

## 🆕 新增文件

1. **app/services/runtime_update_service.py** (220 行)
   - `RuntimeUpdateService` 类：核心更新服务
   - 多实例并发下载管理
   - 进度监控和信号通知
   - 全局单例：`runtimeUpdateService`

2. **app/view/components/runtime_update_cards.py** (178 行)
   - `RuntimeUpdatePrompt` 类：UI 提示管理
   - `BatchRuntimeUpdateCard` 类：批量更新卡片
   - 提供"检查全部更新"和"全部更新"功能

3. **RUNTIME_UPDATE_IMPLEMENTATION.md** (284 行)
   - 完整的实现文档
   - 设计决策和架构说明
   - 使用流程和测试建议

## 🔧 修改的文件

### 核心逻辑
1. **app/services/feature_service.py** (+35 行)
   - 新增 `runtimes()` 方法
   - 遍历所有 Feature Pack 收集 BinaryRuntime 实例

2. **app/startup.py** (+51 行)
   - 新增 `checkRuntimeUpdatesAtStartup()` - 启动时检查
   - 新增 `_cleanupUpdateDirectory()` - 清理临时文件
   - 在 `startEngine()` 和 `stopEngine()` 中调用清理

3. **app/config/paths.py** (+2 行)
   - 新增 `UPDATE_DIR` 常量

### UI 集成
4. **app/view/components/setting_cards.py** (+63 / -27)
   - `RuntimeCard` 类修改：
     - 新增 `_stateToolTip` 成员变量
     - 重写 `_onInstallClicked()` 使用新服务
     - 新增进度回调方法（3个）
     - 集成 `RuntimeUpdateService` 信号

5. **app/view/pages/setting_page.py** (+29 行)
   - 修改 `_initLayout()` 
   - 新增 `_addRuntimeUpdateGroup()` 方法
   - 添加"运行时管理"设置组

### 主程序
6. **Ghost-Downloader-3.py** (+6 / -1)
   - 导入 `checkRuntimeUpdatesAtStartup`
   - 在 `startApp()` 中调用

## 🎯 功能验证清单

### 手动下载
- [ ] 点击任意 RuntimeCard 的"一键安装"按钮
- [ ] StateToolTip 显示实时进度（百分比 + 速度）
- [ ] 下载完成后显示成功 InfoBar
- [ ] 运行时状态自动刷新

### 批量更新
- [ ] 设置页面显示"运行时管理"组
- [ ] 点击"检查全部更新"刷新所有状态
- [ ] 点击"全部更新"启动批量下载
- [ ] 多个运行时同时下载互不干扰

### 并发测试
- [ ] 同时点击多个 RuntimeCard 的安装按钮
- [ ] 每个都显示独立的 StateToolTip
- [ ] 互不影响，各自完成

### 清理机制
- [ ] 启动应用后 update 目录被清空
- [ ] 退出应用后 update 目录被清空
- [ ] 下载的临时文件不会累积

### 异常处理
- [ ] 网络中断时的错误提示
- [ ] 重复点击安装按钮的防护
- [ ] 下载失败后的 InfoBar 提示

## ⚠️ 注意事项

1. **不要从远程拉取** - 远程分支有问题的提交
2. **审核后再推送** - 确认无误后使用 `git push --force`
3. **测试环境** - 建议先在测试环境运行验证

## 📋 推送命令（审核通过后执行）

```bash
# 查看当前状态
git log --oneline -3
git status

# 强制推送到远程（会覆盖远程分支）
git push --force origin feat/update-download-install
```

## 🔍 关键设计点

1. **多实例并发** - 每个 Runtime 有独立的 Task、Timer、StateToolTip
2. **信号驱动** - 松耦合，RuntimeCard 监听 RuntimeUpdateService 的信号
3. **复用 installTask()** - 不重复实现下载逻辑
4. **独立下载模式** - 不进 TaskService，用户体验更好
5. **自动清理** - update 目录启动/退出时清空，避免浪费空间

## ✨ 参考设计

远程分支 baf7c83..1ec147f 的应用更新优化：
- baf7c83: feat(update): 下载并安装软件更新
- 1ec147f: refactor(update): 拆分更新下载为业务/视图两层

采用相同的架构模式但扩展为支持多实例并发。

---

**实现日期**: 2026-07-05
**实现者**: Claude Opus 4.8
**审核状态**: ⏳ 待审核
