import os
import shutil

from conan import ConanFile
from conan.tools.files import get, chdir, apply_conandata_patches, replace_in_file, copy
from conan.tools.layout import basic_layout
from conan.tools.microsoft.visual import VCVars, is_msvc
from conan.tools.gnu import AutotoolsToolchain, Autotools

required_conan_version = ">=1.46.0"


class NASMConan(ConanFile):
    name = "nasm"
    url = "https://github.com/conan-io/conan-center-index"
    homepage = "http://www.nasm.us"
    description = "The Netwide Assembler, NASM, is an 80x86 and x86-64 assembler"
    license = "BSD-2-Clause"
    settings = "os", "arch", "compiler", "build_type"
    topics = ("nasm", "installer", "assembler")

    exports_sources = "patches/*"
    _autotools = None

    def layout(self):
        basic_layout(self, src_folder="source")

    def generate(self):
        at_toolchain = AutotoolsToolchain(self)
        if self.settings.get_safe("compiler") in ["Visual Studio", "msvc"]:
            VCVars(self).generate()
            at_toolchain.configure_args.append("-nologo")
        if self.settings.arch == "x86":
            at_toolchain.cflags.append("-m32")
        elif self.settings.arch == "x86_64":
            at_toolchain.cflags.append("-m64")
        at_toolchain.generate()

    def configure(self):
        try:
            del self.settings.compiler.libcxx
            del self.settings.compiler.cppstd
        except Exception:
            pass

    def build_requirements(self):
        settings_build = getattr(self, "settings_build", self.settings)
        if settings_build.os == "Windows":
            self.tool_requires("strawberryperl/5.30.0.1")

    def source(self):
        get(self, **self.conan_data["sources"][self.version], strip_root=True)

    def package_id(self):
        del self.info.settings.compiler

    def build(self):
        apply_conandata_patches(self)

        if is_msvc(self):
            with chdir(self, self.source_folder):
                #self.run("nmake /f {} {}".format(os.path.join("Mkfiles", "msvc.mak"), " ".join("{}=\"{}\"".format(k, v) for k, v in autotools.vars.items())))
                self.run("nmake /f {}".format(os.path.join("Mkfiles", "msvc.mak")))
                shutil.copy("nasm.exe", "nasmw.exe")
                shutil.copy("ndisasm.exe", "ndisasmw.exe")
        else:
            autotools = Autotools(self)
            autotools.configure()
            # GCC9 - "pure" attribute on function returning "void"
            replace_in_file(self, "Makefile", "-Werror=attributes", "")

            # Need "-arch" flag for the linker when cross-compiling.
            # FIXME: Revisit after https://github.com/conan-io/conan/issues/9069, using new Autotools integration
            if str(self.version).startswith("2.13"):
                replace_in_file(self, "Makefile", "$(CC) $(LDFLAGS) -o", "$(CC) $(ALL_CFLAGS) $(LDFLAGS) -o")
                replace_in_file(self, "Makefile", "$(INSTALLROOT)", "$(DESTDIR)")
            autotools.make()

    def package(self):
        copy(self, "LICENSE", self.source_folder, os.path.join(self.package_folder, "licenses"))
        if self.settings.get_safe("compiler") in ["Visual Studio", "msvc"]:
            copy(self, "*.exe", self.source_folder, os.path.join(self.package_folder, "bin"), keep_path=False)
        else:
            autotools = Autotools(self)
            autotools.install()
            shutil.rmtree(os.path.join(self.package_folder, "res"))

    def package_info(self):
        bin_path = os.path.join(self.package_folder, "bin")
        self.output.info("Appending PATH environment variable: {}".format(bin_path))
        self.buildenv_info.append_path("PATH", bin_path)
