from app.supports import file_association

# 文件关联（gui 端桌面 OS 动作，同开机自启）：把开了「关联」的 pack 声明的文件类型（.torrent/.m3u8 等）
# 注册到系统，双击即用 GD 打开。MemoryLink 模式下 setPackSetting 写 cfg → 开关 valueChanged 当场触发；
# daemon 模式 gui 不加载 pack，此处拿不到关联、不处理（已知取舍）。register/unregister 来自 file_association。


def applyFileAssociations(associations: list[tuple]) -> None:
    for types, associate in associations:
        if associate.value:
            file_association.register(types)
        associate.valueChanged.connect(
            lambda enabled, t=types: file_association.register(t) if enabled else file_association.unregister(t))
