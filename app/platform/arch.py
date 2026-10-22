import platform

ARCH_ALIASES = {"amd64": "x86_64", "x86_64": "x86_64", "arm64": "arm64", "aarch64": "arm64", "arm64_v8a": "arm64"}

MACHINE_ARCH = ARCH_ALIASES[platform.machine().lower()]
