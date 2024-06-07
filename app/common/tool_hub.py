import winreg


def getWindowsProxy():
    try:
        # 打开 Windows 注册表项
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r'Software\Microsoft\Windows\CurrentVersion\Internet Settings')

        # 获取代理开关状态
        proxy_enable, _ = winreg.QueryValueEx(key, 'ProxyEnable')

        if proxy_enable:
            # 获取代理地址和端口号
            proxy_server, _ = winreg.QueryValueEx(key, 'ProxyServer')
            return {
                "http": proxy_server,
                "https": proxy_server,
            }
        else:
            return {
                "http": None,
                "https": None,
            }

    except Exception as e:
        print("获取 Windows 系统代理失败：", e)
        return {
            "http": None,
            "https": None,
        }


def getReadableSize(size):
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    unit_index = 0
    K = 1024.0
    while size >= K:
        size = size / K
        unit_index += 1
    return "%.2f %s" % (size, units[unit_index])
