from pythonforandroid.recipe import RustCompiledComponentsRecipe

class Jh2Recipe(RustCompiledComponentsRecipe):
    version = "5.0.13"
    url = "https://github.com/jawah/h2/archive/refs/tags/v{version}.tar.gz"
    site_packages_name = "jh2"

recipe = Jh2Recipe()
