import os

from conan import ConanFile
from conan.tools.build import check_min_cppstd
from conan.tools.cmake import CMake, cmake_layout, CMakeToolchain
from conan.tools.files import copy, get, apply_conandata_patches, replace_in_file, rmdir
from conan.tools.microsoft import msvc_runtime_flag
from conans.errors import ConanInvalidConfiguration

required_conan_version = ">=1.43.0"


class GTestConan(ConanFile):
    name = "gtest"
    description = "Google's C++ test framework"
    url = "https://github.com/conan-io/conan-center-index"
    homepage = "https://github.com/google/googletest"
    license = "BSD-3-Clause"
    topics = ("testing", "google-testing", "unit-test")

    settings = "os", "arch", "compiler", "build_type"
    options = {
        "shared": [True, False],
        "build_gmock": [True, False],
        "fPIC": [True, False],
        "no_main": [True, False],
        "debug_postfix": ["ANY"],
        "hide_symbols": [True, False],
    }
    default_options = {
        "shared": False,
        "build_gmock": True,
        "fPIC": True,
        "no_main": False,
        "debug_postfix": "d",
        "hide_symbols": False,
    }

    def generate(self):
        toolchain = CMakeToolchain(self)
        if self.settings.build_type == "Debug":
            toolchain.variables["CUSTOM_DEBUG_POSTFIX"] = self.options.debug_postfix
        if self._is_msvc:
            toolchain.variables["gtest_force_shared_crt"] = "MD" in msvc_runtime_flag(self)
        toolchain.variables["BUILD_GMOCK"] = self.options.build_gmock
        if self.settings.os == "Windows" and self.settings.compiler == "gcc":
            toolchain.variables["gtest_disable_pthreads"] = True
        toolchain.generate()

    def layout(self):
        cmake_layout(self)

    @property
    def _is_msvc(self):
        return str(self.settings.compiler) in ["Visual Studio", "msvc"]

    @property
    def _minimum_cpp_standard(self):
        if self.version == "1.8.1":
            return 98
        else:
            return 11

    @property
    def _minimum_compilers_version(self):
        if self.version == "1.8.1":
            return {
                "Visual Studio": "14"
            }
        elif self.version == "1.10.0":
            return {
                "Visual Studio": "14",
                "gcc": "4.8.1",
                "clang": "3.3",
                "apple-clang": "5.0"
            }
        else:
            return {
                "Visual Studio": "14",
                "gcc": "5",
                "clang": "5",
                "apple-clang": "9.1"
            }

    def export_sources(self):
        copy(self, "CMakeLists.txt", self.recipe_folder, self.export_sources_folder)
        for the_patch in self.conan_data.get("patches", {}).get(self.version, []):
            copy(self, the_patch["patch_file"], self.recipe_folder, self.export_sources_folder)

    def config_options(self):
        if self.settings.os == "Windows":
            del self.options.fPIC
        if self.settings.build_type != "Debug":
            del self.options.debug_postfix

    def configure(self):
        if self.options.shared:
            del self.options.fPIC

    def validate(self):
        if self.options.shared and self._is_msvc and "MT" in msvc_runtime_flag(self):
            raise ConanInvalidConfiguration(
                "gtest:shared=True with compiler=\"Visual Studio\" is not "
                "compatible with compiler.runtime=MT/MTd"
            )

        if self.settings.compiler.get_safe("cppstd"):
            check_min_cppstd(self, self._minimum_cpp_standard)

        def loose_lt_semver(v1, v2):
            lv1 = [int(v) for v in v1.split(".")]
            lv2 = [int(v) for v in v2.split(".")]
            min_length = min(len(lv1), len(lv2))
            return lv1[:min_length] < lv2[:min_length]

        min_version = self._minimum_compilers_version.get(str(self.settings.compiler))
        if min_version and loose_lt_semver(str(self.settings.compiler.version), min_version):
            raise ConanInvalidConfiguration(
                "{0} requires {1} {2}. The current compiler is {1} {3}.".format(
                    self.name, self.settings.compiler,
                    min_version, self.settings.compiler.version
                )
            )

    def package_id(self):
        del self.info.options.no_main

    def source(self):
        get(self, **self.conan_data["sources"][self.version], strip_root=True)
        apply_conandata_patches(self)
        # No warnings as errors
        internal_utils = os.path.join(self.source_folder, "googletest", "cmake",
                                      "internal_utils.cmake")
        replace_in_file(self, internal_utils, "-WX", "")
        replace_in_file(self, internal_utils, "-Werror", "")

    def build(self):
        cmake = CMake(self)
        cmake.configure()
        cmake.build()

    def package(self):
        copy(self, "LICENSE", self.source_folder, os.path.join(self.package_folder, "licenses"))
        cmake = CMake(self)
        cmake.install()
        rmdir(self, os.path.join(self.package_folder, "lib", "pkgconfig"))
        rmdir(self, os.path.join(self.package_folder, "lib", "cmake"))
        # rm("*.pdb", os.path.join(self.package_folder, "lib"), recursive=True)

    @property
    def _postfix(self):
        return self.options.debug_postfix if self.settings.build_type == "Debug" else ""

    def package_info(self):
        self.cpp_info.set_property("cmake_find_mode", "both")
        self.cpp_info.set_property("cmake_file_name", "GTest")

        # gtest
        self.cpp_info.components["libgtest"].set_property("cmake_target_name", "GTest::gtest")
        self.cpp_info.components["libgtest"].set_property("cmake_target_aliases", ["GTest::GTest"])
        self.cpp_info.components["libgtest"].set_property("pkg_config_name", "gtest")
        self.cpp_info.components["libgtest"].libdirs = ["lib"]
        self.cpp_info.components["libgtest"].includedirs = ["include"]
        self.cpp_info.components["libgtest"].libs = ["gtest{}".format(self._postfix)]
        if self.settings.os in ["Linux", "FreeBSD"]:
            self.cpp_info.components["libgtest"].system_libs.append("pthread")
        if self.settings.os == "Neutrino" and self.settings.os.version == "7.1":
            self.cpp_info.components["libgtest"].system_libs.append("regex")
        if self.options.shared:
            self.cpp_info.components["libgtest"].defines.append("GTEST_LINKED_AS_SHARED_LIBRARY=1")
        if self.version == "1.8.1":
            if (self.settings.get_safe("compiler") == "Visual Studio" and str(self.settings.compiler.version) >= "15") or \
               (str(self.settings.compiler) == "msvc" and str(self.settings.compiler.version) >= "191"):
                self.cpp_info.components["libgtest"].defines.append("GTEST_LANG_CXX11=1")
                self.cpp_info.components["libgtest"].defines.append("GTEST_HAS_TR1_TUPLE=0")

        # gtest_main
        if not self.options.no_main:
            self.cpp_info.components["gtest_main"].set_property("cmake_target_name", "GTest::gtest_main")
            self.cpp_info.components["gtest_main"].set_property("cmake_target_aliases", ["GTest::Main"])
            self.cpp_info.components["gtest_main"].set_property("pkg_config_name", "gtest_main")
            self.cpp_info.components["gtest_main"].libs = ["gtest_main{}".format(self._postfix)]
            self.cpp_info.components["gtest_main"].libdirs = ["lib"]
            self.cpp_info.components["gtest_main"].includedirs = ["include"]
            self.cpp_info.components["gtest_main"].requires = ["libgtest"]

        # gmock
        if self.options.build_gmock:
            self.cpp_info.components["gmock"].set_property("cmake_target_name", "GTest::gmock")
            self.cpp_info.components["gmock"].set_property("pkg_config_name", "gmock")
            self.cpp_info.components["gmock"].libs = ["gmock{}".format(self._postfix)]
            self.cpp_info.components["gmock"].libdirs = ["lib"]
            self.cpp_info.components["gmock"].includedirs = ["include"]
            self.cpp_info.components["gmock"].requires = ["libgtest"]

            # gmock_main
            if not self.options.no_main:
                self.cpp_info.components["gmock_main"].set_property("cmake_target_name", "GTest::gmock_main")
                self.cpp_info.components["gmock_main"].set_property("pkg_config_name", "gmock_main")
                self.cpp_info.components["gmock_main"].libs = ["gmock_main{}".format(self._postfix)]
                self.cpp_info.components["gmock_main"].libdirs = ["lib"]
                self.cpp_info.components["gmock_main"].includedirs = ["include"]
                self.cpp_info.components["gmock_main"].requires = ["gmock"]
