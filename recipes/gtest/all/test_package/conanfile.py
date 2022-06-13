from conan import ConanFile
from conan.tools.cmake import CMake, CMakeToolchain
from conan.tools.build import cross_building
from conan.tools.cmake import cmake_layout
import os


class TestPackageConan(ConanFile):
    settings = "os", "compiler", "build_type", "arch"
    generators = "CMakeDeps"

    def layout(self):
        cmake_layout(self)

    def requirements(self):
        self.requires(self.tested_reference_str)

    def generate(self):
        toolchain = CMakeToolchain(self)
        toolchain.variables['WITH_GMOCK'] = self.dependencies['gtest'].options["build_gmock"]
        toolchain.variables['WITH_MAIN'] = not self.dependencies['gtest'].options["no_main"]
        toolchain.generate()

    def build(self):
        cmake = CMake(self)

        cmake.configure()
        cmake.build()

    def test(self):
        cpp_info = self.dependencies["gtest"].cpp_info
        assert os.path.isfile(os.path.join(cpp_info.libdirs[0], "..", "licenses", "LICENSE"))
        if not cross_building(self):
            bin_path = os.path.join(self.cpp.build.bindirs[0], "test_package")
            self.run(bin_path)
