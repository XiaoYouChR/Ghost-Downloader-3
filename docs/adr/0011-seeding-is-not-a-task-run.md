# 做种不是 Task Run

BT 与 eD2k 下载完成即结束 Task Run，Task 进入 COMPLETED；随后的 Seeding 是 App 管理生命周期的独立工作，
不占任务槽，不阻塞 Plan、完成通知与睡眠抑制。一个 Task 同时最多一份活跃工作：Task Run 或 Seeding。
App 只知道「已完成的 Task 可以继续服务他人、用户可开关」；分享率、时间上限、peers、上传速率等协议知识留在 pack，
通过 `Task.runSeeding(isManual)` 这一 seam 接入——正常返回表示自行结束，取消表示被停止。

## Considered Options

- **做种期间保持 RUNNING，用 `usesSlot` 豁免槽位**（`d65b373e` 前的做法）：Step RUNNING 而 Task 该算完成，
  状态派生、任务列表、Plan、完成通知都要为此开例外，且违反「零或一个 Task Run」。
- **做种完全留在 pack 内，App 暴露生命周期钩子**：pack 看不到启动、删除、Revive、退出、文件消失这些时刻，
  需要一组 `onCompleted`/`onRemoved`/… 钩子，每个 pack 各自重搭同一台状态机——浅模块，两份实现。

## Consequences

- 正常退出不改 `shouldSeed`，下次启动自动恢复做种；到达上限或用户停止才置 False。
- 用户手动开始做种（`isManual=True`）时 pack 忽略上限。
- `shouldSeed` 默认 False，由 `TaskService.add` 置 True：升级前的 Task Record 没有这个字段，不会在升级后集体开始做种。
- 桌面上做种不阻止睡眠；Android 上做种计入前台保活——前者是「防睡眠」，后者是「防杀进程」。
