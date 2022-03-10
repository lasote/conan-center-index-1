from conan import ConanFile
from conan.tools.cmake import cmake_layout, CMake, CMakeToolchain
from conan.tools.build import cross_building
import os


class TestPackageConan(ConanFile):
    settings = "os", "compiler", "arch", "build_type"
    generators = "CMakeDeps", "PkgConfigDeps"

    def layout(self):
        cmake_layout(self)

    def requirements(self):
        self.requires(self.tested_reference_str)

    def generate(self):
        toolchain = CMakeToolchain(self)
        toolchain.variables["OPENSSL_WITH_ZLIB"] = not self.dependencies["openssl"].options.no_zlib
        if self.settings.os == "Android":
            toolchain.variables["CONAN_LIBCXX"] = ""
        toolchain.generate()
        # FIXME: smell of root package
        license_path = os.path.join(self.dependencies["openssl"].cpp_info.libdirs[0], "..", "licenses", "LICENSE.txt")
        assert os.path.exists(license_path)

    def build(self):
        cmake = CMake(self)
        cmake.configure()
        cmake.build()

    def test(self):
        if not cross_building(self):
            bin_path = os.path.join(self.cpp.build.bindirs[0], "digest")
            self.run(bin_path)

            if not self.dependencies["openssl"].options.no_stdio:
                self.run("openssl version")

        for fn in ("libcrypto.pc", "libssl.pc", "openssl.pc",):
            assert os.path.isfile(os.path.join(self.generators_folder, fn))
