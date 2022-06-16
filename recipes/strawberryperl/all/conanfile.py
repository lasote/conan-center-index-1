import os
import shutil
from conan import ConanFile
from conan.tools.files import get, copy
from conan.tools.layout import basic_layout
from conans.errors import ConanInvalidConfiguration


class StrawberryperlConan(ConanFile):
    name = "strawberryperl"
    description = "Strawbery Perl for Windows. Useful as build_require"
    license = "GNU Public License or the Artistic License"
    homepage = "http://strawberryperl.com"
    url = "https://github.com/conan-io/conan-center-index"
    topics = ("conan", "installer", "perl", "windows")
    settings = "os", "arch"
    short_paths = True

    def layout(self):
        basic_layout(self)

    def configure(self):
        if self.settings.os != "Windows":
            raise ConanInvalidConfiguration("Only windows supported for Strawberry Perl.")

    def build(self):
        arch = str(self.settings.arch)
        url = self.conan_data["sources"][self.version]["url"][arch]
        sha256 = self.conan_data["sources"][self.version]["sha256"][arch]
        get(self, url, sha256=sha256)

    def package(self):
        copy(self, "License.rtf*", "licenses", os.path.join(self.package_folder, "licenses"))
        copy(self, "*", os.path.join("perl", "bin"), os.path.join(self.package_folder, "bin"))
        copy(self, "*", os.path.join("perl", "lib"), os.path.join(self.package_folder, "lib"))
        copy(self, "*", os.path.join("perl", "vendor", "lib"), os.path.join(self.package_folder, "lib"))
        if os.path.exists(os.path.join(self.package_folder, "lib", "pkgconfig")):
            shutil.rmtree(os.path.join(self.package_folder, "lib", "pkgconfig"))

    def package_info(self):
        self.cpp_info.libdirs = []
        self.cpp_info.includedirs = []

        bin_path = os.path.join(self.package_folder, "bin")
        self.output.info("Appending PATH environment variable: %s" % bin_path)
        self.buildenv_info.prepend_path("PATH", bin_path)

