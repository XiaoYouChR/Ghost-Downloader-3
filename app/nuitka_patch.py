from PySide6.QtCore import SignalInstance


class FunctionRefs(list):

    def append(self, method) -> None:
        super().append(method.im_func)


def patchSignalWorkaround() -> None:
    # https://github.com/Nuitka/Nuitka/issues/4108
    namespace = getattr(SignalInstance.connect, "__globals__", {})
    if "_protected" in namespace:
        namespace["_protected"] = FunctionRefs(namespace["_protected"])
