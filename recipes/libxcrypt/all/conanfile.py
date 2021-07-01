import os
from conans import ConanFile, tools
from conans.errors import ConanInvalidConfiguration
from conan.tools.gnu import Autotools, AutotoolsToolchain, AutotoolsDeps
from conan.tools.env import VirtualBuildEnv


class LibxcryptConan(ConanFile):
    name = "libxcrypt"
    url = "https://github.com/conan-io/conan-center-index"
    homepage = "https://github.com/besser82/libxcrypt"
    description = "Extended crypt library for descrypt, md5crypt, bcrypt, and others"
    topics = ("conan", "libxcypt", "hash", "password", "one-way", "bcrypt", "md5", "sha256", "sha512")
    license = ("LGPL-2.1-or-later", )
    settings = "os", "arch", "compiler", "build_type"
    options = {
        "shared": [True, False],
        "fPIC": [True, False],
    }
    default_options = {
        "shared": False,
        "fPIC": True,
    }
    apply_env = False
    win_shell = True

    def build_requirements(self):
        self.build_requires("libtool/2.4.6")

    def layout(self):
        self.folders.source = "{}-{}".format(self.name, self.version)

    def config_options(self):
        if self.settings.os == "Windows":
            del self.options.fPIC
        del self.settings.compiler.libcxx
        del self.settings.compiler.cppstd

    def configure(self):
        if self.settings.compiler == "Visual Studio":
            raise ConanInvalidConfiguration("libxcrypt does not support Visual Studio")
        if self.options.shared:
            del self.options.fPIC

    def generate(self):
        toolchain = AutotoolsToolchain(self)
        conf_args = [
            "--disable-werror",
        ]
        if self.options.shared:
            conf_args.extend(["--enable-shared", "--disable-static"])
        else:
            conf_args.extend(["--disable-shared", "--enable-static"])
        toolchain.configure_args.extend(conf_args)
        toolchain.generate()

        deps = AutotoolsDeps(self)
        deps.generate()

        env_deps = VirtualBuildEnv(self)
        env_deps.generate()

    def source(self):
        tools.get(**self.conan_data["sources"][self.version])

    def build(self):
        tools.replace_in_file(os.path.join(self.source_folder, "Makefile.am"),
                              "\nlibcrypt_la_LDFLAGS = ", "\nlibcrypt_la_LDFLAGS = -no-undefined ")
        with tools.chdir(self.source_folder):
            self.run("autoreconf -fiv")
        autotools = Autotools(self)
        autotools.configure()
        if self.settings.os == "Windows":
            tools.replace_in_file("libtool", "-DPIC", "")
        autotools.make()

    def package(self):
        self.copy("COPYING.LIB", src=self.source_folder, dst="licenses")
        autotools = Autotools(self)
        autotools.install()

        os.unlink(os.path.join(self.package_folder, "lib", "libcrypt.la"))
        tools.rmdir(os.path.join(self.package_folder, "lib", "pkgconfig"))
        tools.rmdir(os.path.join(self.package_folder, "share"))

    def package_info(self):
        self.cpp_info.libs = ["crypt"]
