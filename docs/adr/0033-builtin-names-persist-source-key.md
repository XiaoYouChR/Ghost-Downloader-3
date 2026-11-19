# 内置可编辑名称在配置中持久化源文 key

内置分类（Category）与预设（Headers Preset、Identity Preset）的名称在配置中保留规范中文源文，由逻辑层通过 `N(context, text)` 标注并经 `ENGINE_CONTEXTS` 同步到 Android；桌面端与 Android 端的 View 层在展示时按当前语言查表翻译，编辑页保存时若用户输入未偏离初始译文则回写原中文 key。选择该方案而非引入 `builtInKey` / `customName` 字段拆分，是为了零迁移修复已有用户配置、天然兼容 Android 运行时切换语言，并把逻辑层与 UI 语言彻底解耦。
