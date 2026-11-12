from __future__ import annotations

import math
import os
from collections.abc import Callable
from ctypes import (
    CDLL,
    CFUNCTYPE,
    POINTER,
    Structure,
    Union,
    addressof,
    c_char_p,
    c_int,
    c_int16,
    c_int32,
    c_uint,
    c_uint8,
    c_uint16,
    c_uint32,
    c_void_p,
)
from dataclasses import dataclass
from functools import cache

from loguru import logger
from PySide6.QtCore import QEvent, QObject
from PySide6.QtGui import QGuiApplication, QPlatformSurfaceEvent, QWindow

PADDING = (30, 25, 30, 35)

WL_MARSHAL_FLAG_DESTROY = 1
WL_SHM_FORMAT_ARGB8888 = 0
SHADOW_COMMIT, SHADOW_ATTACH_LEFT, SHADOW_SET_LEFT_OFFSET, SHADOW_DESTROY = 0, 1, 9, 13
MANAGER_CREATE = 0


@dataclass(frozen=True)
class Tile:
    width: int
    height: int
    pixels: bytes


@dataclass(frozen=True)
class Tiles:
    left: Tile
    topLeft: Tile
    top: Tile
    topRight: Tile
    right: Tile
    bottomRight: Tile
    bottom: Tile
    bottomLeft: Tile


def registerWindow(window: QWindow) -> None:
    platform = QGuiApplication.platformName()
    if platform.startswith("wayland"):
        kwinShadow = createKwinShadow()
        if kwinShadow is not None:
            WindowShadow(window, kwinShadow)
    elif platform == "xcb":
        setX11Shadow = createX11Shadow()
        if setX11Shadow is not None:
            setX11Shadow(window)


class WindowShadow(QObject):
    def __init__(self, window: QWindow, kwinShadow: KwinShadow):
        super().__init__(window)
        self._kwinShadow = kwinShadow
        self._shadow: int | None = None
        window.installEventFilter(self)

    def eventFilter(self, window: QWindow, event: QEvent) -> bool:
        eventType = event.type()
        # 隐藏时 Qt 回收 wl_surface 却不发 PlatformSurface 事件
        isSurfaceGone = eventType == QEvent.Type.Hide or (
            eventType == QEvent.Type.PlatformSurface
            and event.surfaceEventType() == QPlatformSurfaceEvent.SurfaceEventType.SurfaceAboutToBeDestroyed
        )
        if self._shadow is None and eventType == QEvent.Type.Expose and window.isExposed():
            self._shadow = self._kwinShadow.create(window)
        elif self._shadow is not None and isSurfaceGone:
            self._kwinShadow.destroy(self._shadow)
            self._shadow = None
        return False


def buildTiles() -> Tiles:
    left, top, right, bottom = PADDING
    # Breeze Large 档
    layers = ((10.0, 5, 0.22), (5.0, 2, 0.12))
    inset = 35

    def cdf(z: float) -> float:
        return 0.5 * (1 + math.erf(z / math.sqrt(2)))

    def horizontal(x: int, side: str, sigma: float) -> float:
        if side == "middle":
            return 1.0
        if side == "left":
            return cdf((x + 0.5) / sigma)
        return cdf(-(x + 0.5) / sigma)

    def vertical(y: int, side: str, sigma: float, offset: int) -> float:
        if side == "middle":
            return 1.0
        if side == "top":
            return cdf((y + 0.5 - offset) / sigma)
        return cdf((offset - y - 0.5) / sigma)

    def build(columns: range, columnSide: str, rows: range, rowSide: str) -> Tile:
        falloffs = [
            (opacity, [horizontal(x, columnSide, sigma) for x in columns],
             [vertical(y, rowSide, sigma, offset) for y in rows])
            for sigma, offset, opacity in layers
        ]
        pixels = bytearray(len(columns) * len(rows) * 4)
        index = 3
        for row in range(len(rows)):
            for column in range(len(columns)):
                transparency = 1.0
                for opacity, xs, ys in falloffs:
                    transparency *= 1 - opacity * xs[column] * ys[row]
                pixels[index] = round(255 * (1 - transparency))
                index += 4
        return Tile(len(columns), len(rows), bytes(pixels))

    leftColumns, rightColumns, middle = range(-left, inset), range(-inset, right), range(1)
    topRows, bottomRows = range(-top, inset), range(-inset, bottom)
    return Tiles(
        left=build(range(-left, 0), "left", middle, "middle"),
        topLeft=build(leftColumns, "left", topRows, "top"),
        top=build(middle, "middle", range(-top, 0), "top"),
        topRight=build(rightColumns, "right", topRows, "top"),
        right=build(range(right), "right", middle, "middle"),
        bottomRight=build(rightColumns, "right", bottomRows, "bottom"),
        bottom=build(middle, "middle", range(bottom), "bottom"),
        bottomLeft=build(leftColumns, "left", bottomRows, "bottom"),
    )


class WlMessage(Structure):
    _fields_ = [("name", c_char_p), ("signature", c_char_p), ("types", POINTER(c_void_p))]


class WlInterface(Structure):
    _fields_ = [
        ("name", c_char_p), ("version", c_int),
        ("method_count", c_int), ("methods", POINTER(WlMessage)),
        ("event_count", c_int), ("events", POINTER(WlMessage)),
    ]


class WlArgument(Union):
    _fields_ = [("i", c_int32), ("s", c_char_p), ("o", c_void_p)]


GlobalListener = CFUNCTYPE(None, c_void_p, c_void_p, c_uint32, c_char_p, c_uint32)
GlobalRemoveListener = CFUNCTYPE(None, c_void_p, c_void_p, c_uint32)


class RegistryListener(Structure):
    _fields_ = [("global_", GlobalListener), ("global_remove", GlobalRemoveListener)]


# 协议定义见 https://invent.kde.org/libraries/plasma-wayland-protocols/-/blob/master/src/protocols/shadow.xml
class Protocol:
    def __init__(self, wayland: CDLL):
        surfaceInterface = addressof(WlInterface.in_dll(wayland, "wl_surface_interface"))
        bufferInterface = addressof(WlInterface.in_dll(wayland, "wl_buffer_interface"))
        self._arrays = []  # 代理存活期间不能释放这些结构
        self.shadow = self._buildInterface(b"org_kde_kwin_shadow", 2, [
            (b"commit", b"", []),
            *[(b"attach_" + side, b"o", [bufferInterface]) for side in (
                b"left", b"top_left", b"top", b"top_right", b"right", b"bottom_right", b"bottom", b"bottom_left")],
            *[(b"set_" + side + b"_offset", b"f", [None]) for side in (b"left", b"top", b"right", b"bottom")],
            (b"destroy", b"2", []),
        ])
        self.manager = self._buildInterface(b"org_kde_kwin_shadow_manager", 2, [
            (b"create", b"no", [addressof(self.shadow), surfaceInterface]),
            (b"unset", b"o", [surfaceInterface]),
            (b"destroy", b"2", []),
        ])

    def _buildInterface(self, name: bytes, version: int, methods: list[tuple[bytes, bytes, list]]) -> WlInterface:
        messages = (WlMessage * len(methods))()
        self._arrays.append(messages)
        for message, (methodName, signature, types) in zip(messages, methods):
            typeArray = (c_void_p * max(len(types), 1))(*types)
            self._arrays.append(typeArray)
            message.name, message.signature, message.types = methodName, signature, typeArray
        return WlInterface(name, version, len(methods), messages, 0, None)


def marshal(wayland: CDLL, proxy: int, opcode: int, args: list, interface: WlInterface | None = None,
            version: int = 0, flags: int = 0) -> int:
    array = (WlArgument * max(len(args), 1))()
    for argument, value in zip(array, args):
        if isinstance(value, bytes):
            argument.s = value
        elif isinstance(value, float):
            argument.i = round(value * 256)
        elif isinstance(value, int):
            argument.i = value
        else:
            argument.o = value
    if interface is not None and not version:
        version = wayland.wl_proxy_get_version(proxy)
    return wayland.wl_proxy_marshal_array_flags(
        proxy, opcode, addressof(interface) if interface is not None else None, version, flags, array,
    )


class KwinShadow:
    def __init__(self, wayland: CDLL, display: int, surfaceByWindow, protocol: Protocol,
                 manager: int, managerVersion: int, buffers: list[int]):
        self._wayland = wayland
        self._display = display
        self._surfaceByWindow = surfaceByWindow
        self._protocol = protocol
        self._manager = manager
        self._managerVersion = managerVersion
        self._buffers = buffers

    def create(self, window: QWindow) -> int | None:
        surface = self._surfaceByWindow(window)
        if not surface:
            return None
        wayland = self._wayland
        shadow = marshal(wayland, self._manager, MANAGER_CREATE, [None, c_void_p(surface)], self._protocol.shadow)
        for opcode, buffer in enumerate(self._buffers, start=SHADOW_ATTACH_LEFT):
            marshal(wayland, shadow, opcode, [c_void_p(buffer)])
        for opcode, offset in enumerate(PADDING, start=SHADOW_SET_LEFT_OFFSET):
            marshal(wayland, shadow, opcode, [float(offset)])
        marshal(wayland, shadow, SHADOW_COMMIT, [])
        wayland.wl_display_flush(self._display)
        # 阴影随下一次 commit 生效
        window.requestUpdate()
        return shadow

    def destroy(self, shadow: int) -> None:
        if self._managerVersion >= 2:
            marshal(self._wayland, shadow, SHADOW_DESTROY, [], flags=WL_MARSHAL_FLAG_DESTROY)
        else:
            self._wayland.wl_proxy_destroy(shadow)
        self._wayland.wl_display_flush(self._display)


@cache
def createKwinShadow() -> KwinShadow | None:
    import shiboken6

    # Qt 没有获取 wl_surface 的公开接口，见 ADR 0030
    try:
        wayland = CDLL("libwayland-client.so.0")
        resolveInterface = CDLL("libQt6Gui.so.6")["_ZNK7QWindow16resolveInterfaceEPKci"]
        wlSurface = CDLL("libQt6WaylandClient.so.6")["_ZNK15QtWaylandClient14QWaylandWindow9wlSurfaceEv"]
        wayland.wl_proxy_marshal_array_flags  # noqa: B018 libwayland 1.20 起提供
    except (OSError, AttributeError) as e:
        logger.warning("无法加载窗口阴影所需的符号: {}", e)
        return None

    resolveInterface.restype, resolveInterface.argtypes = c_void_p, [c_void_p, c_char_p, c_int]
    wlSurface.restype, wlSurface.argtypes = c_void_p, [c_void_p]
    wayland.wl_proxy_marshal_array_flags.restype = c_void_p
    wayland.wl_proxy_marshal_array_flags.argtypes = [c_void_p, c_uint32, c_void_p, c_uint32, c_uint32, POINTER(WlArgument)]
    wayland.wl_proxy_create_wrapper.restype = c_void_p
    wayland.wl_display_create_queue.restype = c_void_p
    for name in ("wl_proxy_get_version", "wl_proxy_create_wrapper", "wl_proxy_wrapper_destroy",
                 "wl_proxy_destroy", "wl_display_flush", "wl_display_create_queue"):
        getattr(wayland, name).argtypes = [c_void_p]
    for name in ("wl_proxy_set_queue", "wl_display_roundtrip_queue"):
        getattr(wayland, name).argtypes = [c_void_p, c_void_p]
    wayland.wl_proxy_add_listener.argtypes = [c_void_p, c_void_p, c_void_p]

    def surfaceByWindow(window: QWindow) -> int | None:
        # 私有接口是 QWaylandWindow 的第一个基类，两者地址相同；接口名不含命名空间
        native = resolveInterface(shiboken6.getCppPointer(window)[0], b"QWaylandWindow", 1)
        return wlSurface(native) if native else None

    def interface(name: str) -> WlInterface:
        return WlInterface.in_dll(wayland, name)

    display = QGuiApplication.instance().nativeInterface().display()
    advertised: dict[bytes, tuple[int, int]] = {}

    def onGlobal(data, registry, name, interfaceName, version):
        advertised[interfaceName] = (name, version)

    listener = RegistryListener(GlobalListener(onGlobal), GlobalRemoveListener(lambda *_: None))
    queue = wayland.wl_display_create_queue(display)
    wrapper = wayland.wl_proxy_create_wrapper(display)
    wayland.wl_proxy_set_queue(wrapper, queue)
    registry = marshal(wayland, wrapper, 1, [None], interface("wl_registry_interface"))
    wayland.wl_proxy_wrapper_destroy(wrapper)
    wayland.wl_proxy_add_listener(registry, addressof(listener), None)
    wayland.wl_display_roundtrip_queue(display, queue)

    if b"org_kde_kwin_shadow_manager" not in advertised or b"wl_shm" not in advertised:
        wayland.wl_proxy_destroy(registry)
        return None

    def bind(name: bytes, boundInterface: WlInterface, maxVersion: int) -> tuple[int, int]:
        globalName, version = advertised[name]
        version = min(version, maxVersion)
        return marshal(wayland, registry, 0, [globalName, name, version, None], boundInterface, version), version

    protocol = Protocol(wayland)
    manager, managerVersion = bind(b"org_kde_kwin_shadow_manager", protocol.manager, 2)
    shm, _ = bind(b"wl_shm", interface("wl_shm_interface"), 1)
    wayland.wl_proxy_destroy(registry)

    built = buildTiles()
    tiles = (built.left, built.topLeft, built.top, built.topRight,
             built.right, built.bottomRight, built.bottom, built.bottomLeft)
    fd = os.memfd_create("ghost-downloader-shadow")
    try:
        for tile in tiles:
            os.write(fd, tile.pixels)
        pool = marshal(wayland, shm, 0, [None, fd, sum(len(tile.pixels) for tile in tiles)],
                       interface("wl_shm_pool_interface"))
    finally:
        os.close(fd)
    buffers, offset = [], 0
    for tile in tiles:
        buffers.append(marshal(wayland, pool, 0, [None, offset, tile.width, tile.height, tile.width * 4,
                                                  WL_SHM_FORMAT_ARGB8888], interface("wl_buffer_interface")))
        offset += len(tile.pixels)
    marshal(wayland, pool, 1, [], flags=WL_MARSHAL_FLAG_DESTROY)
    wayland.wl_display_flush(display)
    return KwinShadow(wayland, display, surfaceByWindow, protocol, manager, managerVersion, buffers)


class XcbScreenIterator(Structure):
    _fields_ = [("data", POINTER(c_uint32)), ("rem", c_int), ("index", c_int)]


class XcbInternAtomReply(Structure):
    _fields_ = [("response_type", c_uint8), ("pad0", c_uint8), ("sequence", c_uint16),
                ("length", c_uint32), ("atom", c_uint32)]


XCB_ATOM_ATOM, XCB_ATOM_CARDINAL = 4, 6
XCB_PROP_MODE_REPLACE, XCB_IMAGE_FORMAT_Z_PIXMAP = 0, 2


@cache
def createX11Shadow() -> Callable[[QWindow], None] | None:
    try:
        xcb = CDLL("libxcb.so.1")
    except OSError as e:
        logger.warning("无法加载窗口阴影所需的 libxcb: {}", e)
        return None
    free = CDLL(None).free
    free.argtypes = [c_void_p]

    # cookie 是只含一个 unsigned int 的结构体，按值传递时与 c_uint 一致
    xcb.xcb_get_setup.restype = c_void_p
    xcb.xcb_get_setup.argtypes = [c_void_p]
    xcb.xcb_setup_roots_iterator.restype = XcbScreenIterator
    xcb.xcb_setup_roots_iterator.argtypes = [c_void_p]
    xcb.xcb_intern_atom.restype = c_uint
    xcb.xcb_intern_atom.argtypes = [c_void_p, c_uint8, c_uint16, c_char_p]
    xcb.xcb_intern_atom_reply.restype = POINTER(XcbInternAtomReply)
    xcb.xcb_intern_atom_reply.argtypes = [c_void_p, c_uint, c_void_p]
    xcb.xcb_get_property.restype = c_uint
    xcb.xcb_get_property.argtypes = [c_void_p, c_uint8, c_uint32, c_uint32, c_uint32, c_uint32, c_uint32]
    xcb.xcb_get_property_reply.restype = c_void_p
    xcb.xcb_get_property_reply.argtypes = [c_void_p, c_uint, c_void_p]
    xcb.xcb_get_property_value.restype = POINTER(c_uint32)
    xcb.xcb_get_property_value.argtypes = [c_void_p]
    xcb.xcb_get_property_value_length.restype = c_int
    xcb.xcb_get_property_value_length.argtypes = [c_void_p]
    xcb.xcb_generate_id.restype = c_uint32
    xcb.xcb_generate_id.argtypes = [c_void_p]
    xcb.xcb_create_pixmap.argtypes = [c_void_p, c_uint8, c_uint32, c_uint32, c_uint16, c_uint16]
    xcb.xcb_create_gc.argtypes = [c_void_p, c_uint32, c_uint32, c_uint32, c_void_p]
    xcb.xcb_put_image.argtypes = [c_void_p, c_uint8, c_uint32, c_uint32, c_uint16, c_uint16,
                                  c_int16, c_int16, c_uint8, c_uint8, c_uint32, c_char_p]
    xcb.xcb_free_gc.argtypes = [c_void_p, c_uint32]
    xcb.xcb_change_property.argtypes = [c_void_p, c_uint8, c_uint32, c_uint32, c_uint32, c_uint8, c_uint32, c_void_p]
    xcb.xcb_flush.argtypes = [c_void_p]

    connection = QGuiApplication.instance().nativeInterface().connection()
    root = xcb.xcb_setup_roots_iterator(xcb.xcb_get_setup(connection)).data[0]

    def internAtom(name: bytes) -> int:
        reply = xcb.xcb_intern_atom_reply(connection, xcb.xcb_intern_atom(connection, 0, len(name), name), None)
        if not reply:
            return 0
        atom = reply.contents.atom
        free(reply)
        return atom

    def supportedAtoms() -> set[int]:
        netSupported = internAtom(b"_NET_SUPPORTED")
        reply = xcb.xcb_get_property_reply(
            connection, xcb.xcb_get_property(connection, 0, root, netSupported, XCB_ATOM_ATOM, 0, 4096), None)
        if not reply:
            return set()
        values = xcb.xcb_get_property_value(reply)
        atoms = {values[i] for i in range(xcb.xcb_get_property_value_length(reply) // 4)}
        free(reply)
        return atoms

    atom = internAtom(b"_KDE_NET_WM_SHADOW")
    if atom not in supportedAtoms():
        return None

    built = buildTiles()
    pixmaps = []
    for tile in (built.top, built.topRight, built.right, built.bottomRight,
                 built.bottom, built.bottomLeft, built.left, built.topLeft):
        pixmap, gc = xcb.xcb_generate_id(connection), xcb.xcb_generate_id(connection)
        xcb.xcb_create_pixmap(connection, 32, pixmap, root, tile.width, tile.height)
        xcb.xcb_create_gc(connection, gc, pixmap, 0, None)
        xcb.xcb_put_image(connection, XCB_IMAGE_FORMAT_Z_PIXMAP, pixmap, gc, tile.width, tile.height,
                          0, 0, 0, 32, len(tile.pixels), tile.pixels)
        xcb.xcb_free_gc(connection, gc)
        pixmaps.append(pixmap)
    left, top, right, bottom = PADDING
    data = (c_uint32 * 12)(*pixmaps, top, right, bottom, left)
    xcb.xcb_flush(connection)

    def setShadow(window: QWindow) -> None:
        # 隐藏不会改变 X 窗口 ID，属性只需设置一次
        xcb.xcb_change_property(connection, XCB_PROP_MODE_REPLACE, window.winId(), atom,
                                XCB_ATOM_CARDINAL, 32, len(data), data)
        xcb.xcb_flush(connection)

    return setShadow
