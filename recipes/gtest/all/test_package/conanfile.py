from conan import ConanFile
from conan.tools.cmake import CMake, CMakeToolchain, cmake_layout
from conan.tools.build import cross_building
from conan.tools.files import save, load
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

        # Access to dependencies should be done in generate
        license_path = self.dependencies["gtest"].cpp_info.get_property("license_path")
        save(self, os.path.join(self.generators_folder, "license_path.txt"), license_path)

    def build(self):
        cmake = CMake(self)

        cmake.configure()
        cmake.build()

    def test(self):
        license_path = load(self, os.path.join(self.generators_folder, "license_path.txt"))
        assert os.path.isfile(license_path)

        if not cross_building(self):
            bin_path = os.path.join(self.cpp.build.bindirs[0], "test_package")
            self.run(bin_path)
