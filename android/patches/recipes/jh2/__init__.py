"""jh2(jawah/h2) —— urllib3-future 的硬依赖(HTTP/2 + HPACK)。

纯 pyo3 abi3、无 C 原生依赖, 故 RustCompiledComponentsRecipe 的标准交叉编译直接够用, 只需声明版本/源/包名。
"""

from pythonforandroid.recipe import RustCompiledComponentsRecipe


class Jh2Recipe(RustCompiledComponentsRecipe):
    version = "5.0.13"
    url = "https://github.com/jawah/h2/archive/refs/tags/v{version}.tar.gz"
    site_packages_name = "jh2"


recipe = Jh2Recipe()
