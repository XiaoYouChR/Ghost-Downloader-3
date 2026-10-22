import platform
import sysconfig

ARCH_ALIASES = {"amd64": "x86_64", "x86_64": "x86_64", "arm64": "arm64", "aarch64": "arm64", "arm64_v8a": "arm64"}

MACHINE_ARCH = ARCH_ALIASES[platform.machine().lower()]
# Windows 上 platform.machine() 查询 WMI，x64 程序跑在 ARM 上也返回 ARM64；BUILD_ARCH 取解释器自身的架构
BUILD_ARCH = ARCH_ALIASES[sysconfig.get_platform().rsplit("-", 1)[1]]
