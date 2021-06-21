from conans import ConanFile, AutoToolsBuildEnvironment, tools
from conans.errors import ConanException, ConanInvalidConfiguration, ConanExceptionInUserConanfileMethod
from conan.tools.gnu import Autotools, AutotoolsToolchain
from conan.tools.files import load_build_json, save_build_json
from conan.tools.microsoft.toolchain import write_conanvcvars

import os

required_conan_version = ">=1.37.0"


class TkConan(ConanFile):
    name = "tk"
    description = "Tk is a graphical user interface toolkit that takes developing desktop applications to a higher level than conventional approaches."
    topics = ("conan", "tk", "gui", "tcl", "scripting", "programming")
    homepage = "https://tcl.tk"
    license = "TCL"
    url = "https://github.com/conan-io/conan-center-index"
    settings = "os", "compiler", "build_type", "arch"
    options = {
        "shared": [True, False],
        "fPIC": [True, False],
    }
    default_options = {
        "shared": False,
        "fPIC": True,
    }

    def generate(self):
        toolchain = AutotoolsToolchain(self)
        if self.settings.os == "Windows":
            toolchain.defines.extend(["UNICODE", "_UNICODE", "_ATL_XP_TARGETING"])
        toolchain.libs = []

        yes_no = lambda v: "yes" if v else "no"
        tcl_root = self.dependencies.host["tcl"].package_folder
        tcl_config = "{}/lib".format(tcl_root).replace("\\", "/")
        configure_args = [
            "--with-tcl={}".format(tools.unix_path(tcl_config)),
            "--enable-threads",
            "--enable-shared={}".format(yes_no(self.options.shared)),
            "--enable-symbols={}".format(yes_no(self.settings.build_type == "Debug")),
            "--enable-64bit={}".format(yes_no(self.settings.arch == "x86_64")),
            "--with-x={}".format(yes_no(self.settings.os == "Linux")),
            "--enable-aqua={}".format(yes_no(tools.is_apple_os(self.settings.os))),
        ]
        toolchain.configure_args = configure_args
        toolchain.make_args = ["TCL_GENERIC_DIR={}".format(os.path.join(tcl_root, "include")).replace("\\", "/")]
        toolchain.generate()

        if self.settings.compiler == "Visual Studio":
            cmd = self._generate_nmake_command()
            data = load_build_json(self)
            data["nmake_args"] = cmd
            save_build_json(self, data)
            write_conanvcvars(self)

    def build(self):
        self._patch_sources()

        if self.settings.compiler == "Visual Studio":
            # LOAD JSON DATA
            data = load_build_json(self)
            args = data["nmake_args"]
            cmd = "nmake {} release".format(args)
            self.run(cmd, cwd=self.source_folder,
                     env=["conanbuildenv", "conanautotoolstoolchain", "conanautotoolsdeps", "conanvcvars"])
        else:
            autotools = Autotools(self)
            autotools.configure()
            autotools.make()

    def _generate_nmake_command(self):
        # https://core.tcl.tk/tips/doc/trunk/tip/477.md
        opts = []
        if not self.options.shared:
            opts.append("static")
        if self.settings.build_type == "Debug":
            opts.append("symbols")
        if "MD" in str(self.settings.compiler.runtime):
            opts.append("msvcrt")
        else:
            opts.append("nomsvcrt")
        if "d" not in str(self.settings.compiler.runtime):
            opts.append("unchecked")
        # https://core.tcl.tk/tk/tktview?name=3d34589aa0
        # https://wiki.tcl-lang.org/page/Building+with+Visual+Studio+2017
        tcl_lib_path = os.path.join(self.dependencies.host["tcl"].package_folder, "lib")
        tclimplib, tclstublib = None, None
        for lib in os.listdir(tcl_lib_path):
            if not lib.endswith(".lib"):
                continue
            if lib.startswith("tcl{}".format("".join(self.version.split(".")[:2]))):
                tclimplib = os.path.join(tcl_lib_path, lib)
            elif lib.startswith("tclstub{}".format("".join(self.version.split(".")[:2]))):
                tclstublib = os.path.join(tcl_lib_path, lib)

        if tclimplib is None or tclstublib is None:
            raise ConanException("tcl dependency misses tcl and/or tclstub library")

        tcldir = self.dependencies.host["tcl"].package_folder.replace("/", "\\\\")
        args = '-nologo -f "{cfgdir}/makefile.vc" INSTALLDIR="{pkgdir}" OPTS={opts} TCLDIR="{tcldir}" ' \
               'TCL_LIBRARY="{tcl_library}" TCLIMPLIB="{tclimplib}" TCLSTUBLIB="{tclstublib}"'.format(
                cfgdir=self.source_folder,
                pkgdir=self.package_folder,
                opts=",".join(opts),
                tcldir=tcldir,
                tclstublib=tclstublib,
                tclimplib=tclimplib,
                tcl_library=self.dependencies.host["tcl"]._conanfile.env_info.TCL_LIBRARY.replace("\\", "/")
            )
        return args

    def layout(self):
        if tools.is_apple_os(self.settings.os):
            source_subfolder = "macosx"
        elif self.settings.os in ("Linux", "FreeBSD"):
            source_subfolder = "unix"
        elif self.settings.os == "Windows":
            source_subfolder = "win"
        else:
            raise ValueError("tk recipe does not recognize os")

        self.folders.source = "tk{}/{}".format(self.version, source_subfolder)

    def source(self):
        tools.get(**self.conan_data["sources"][self.version])

    def config_options(self):
        if self.settings.os == "Windows":
            del self.options.fPIC

    def configure(self):
        if self.options.shared:
            del self.options.fPIC
        del self.settings.compiler.libcxx
        del self.settings.compiler.cppstd

    def requirements(self):
        self.requires("tcl/{}".format(self.version))
        if self.settings.os == "Linux":
            self.requires("fontconfig/2.13.92")
            self.requires("xorg/system")

    def build_requirements(self):
        if self.settings.compiler != "Visual Studio":
            if tools.os_info.is_windows and not tools.get_env("CONAN_BASH_PATH"):
                self.build_requires("msys2/20200517")

    def validate(self):
        if self.options["tcl"].shared != self.options.shared:
            raise ConanInvalidConfiguration("The shared option of tcl and tk must have the same value")

    def _patch_sources(self):
        if self.settings.os != "Windows":
            # When disabling 64-bit support (in 32-bit), this test must be 0 in order to use "long long" for 64-bit ints
            # (${tcl_type_64bit} can be either "__int64" or "long long")
            tools.replace_in_file(os.path.join(self.source_folder, "configure"),
                                  "(sizeof(${tcl_type_64bit})==sizeof(long))",
                                  "(sizeof(${tcl_type_64bit})!=sizeof(long))")
        else:
            makefile_in = os.path.join(self.source_folder, "Makefile.in")
            # Avoid clearing CFLAGS and LDFLAGS in the makefile
            # tools.replace_in_file(makefile_in, "\nCFLAGS{}".format(" " if (build_system == "win" and name == "tcl") else "\t"), "\n#CFLAGS\t")
            tools.replace_in_file(makefile_in, "\nLDFLAGS\t", "\n#LDFLAGS\t")
            tools.replace_in_file(makefile_in, "${CFLAGS}", "${CFLAGS} ${CPPFLAGS}")

            rules_ext_vc = os.path.join(self.source_folder, "rules-ext.vc")
            tools.replace_in_file(rules_ext_vc,
                                  "\n_RULESDIR = ",
                                  "\n_RULESDIR = .\n#_RULESDIR = ")
            rules_vc = os.path.join(self.source_folder, "rules.vc")
            tools.replace_in_file(rules_vc,
                                  r"$(_TCLDIR)\generic",
                                  r"$(_TCLDIR)\include")
            tools.replace_in_file(rules_vc,
                                  "\nTCLSTUBLIB",
                                  "\n#TCLSTUBLIB")
            tools.replace_in_file(rules_vc,
                                  "\nTCLIMPLIB",
                                  "\n#TCLIMPLIB")

            win_makefile_in = os.path.join(self.source_folder, "Makefile.in")
            tools.replace_in_file(win_makefile_in, "\nTCL_GENERIC_DIR", "\n#TCL_GENERIC_DIR")

            win_rules_vc = os.path.join(self.source_folder, "rules.vc")
            tools.replace_in_file(win_rules_vc,
                                  "\ncwarn = $(cwarn) -WX",
                                  "\n# cwarn = $(cwarn) -WX")
            # disable whole program optimization to be portable across different MSVC versions.
            # See conan-io/conan-center-index#4811 conan-io/conan-center-index#4094
            tools.replace_in_file(
                win_rules_vc,
                "OPTIMIZATIONS  = $(OPTIMIZATIONS) -GL",
                "# OPTIMIZATIONS  = $(OPTIMIZATIONS) -GL")

    def package(self):
        self.copy(pattern="license.terms", dst="licenses")
        if self.settings.compiler == "Visual Studio":
            data = load_build_json(self)
            args = data["nmake_args"]
            cmd = "nmake {} install".format(args)
            self.run(cmd, cwd=self.source_folder,
                     env=["conanbuildenv", "conanautotoolstoolchain", "conanautotoolsdeps", "conanvcvars"])
        else:
            with tools.chdir(self.build_folder):
                autotools = Autotools(self)
                autotools.install()
                autotools.make(target="install-private-headers")
                tools.rmdir(os.path.join(self.package_folder, "lib", "pkgconfig"))
        tools.rmdir(os.path.join(self.package_folder, "man"))
        tools.rmdir(os.path.join(self.package_folder, "share"))

        # FIXME: move to patch
        tkConfigShPath = os.path.join(self.package_folder, "lib", "tkConfig.sh")
        if os.path.exists(tkConfigShPath):
            pkg_path = os.path.join(self.package_folder).replace('\\', '/')
            tools.replace_in_file(tkConfigShPath, pkg_path, "${TK_ROOT}")
            tools.replace_in_file(tkConfigShPath, "\nTK_BUILD_", "\n#TK_BUILD_")
            tools.replace_in_file(tkConfigShPath, "\nTK_SRC_DIR", "\n#TK_SRC_DIR")

    def package_info(self):
        if self.settings.compiler == "Visual Studio":
            tk_version = tools.Version(self.version)
            lib_infix = "{}{}".format(tk_version.major, tk_version.minor)
            tk_suffix = "t{}{}{}".format(
                "" if self.options.shared else "s",
                "g" if self.settings.build_type == "Debug" else "",
                "x" if "MD" in str(self.settings.compiler.runtime) and not self.options.shared else "",
            )
        else:
            tk_version = tools.Version(self.version)
            lib_infix = "{}.{}".format(tk_version.major, tk_version.minor)
            tk_suffix = ""
        self.cpp_info.libs = ["tk{}{}".format(lib_infix, tk_suffix), "tkstub{}".format(lib_infix)]
        if self.settings.os == "Macos":
            self.cpp_info.frameworks = ["CoreFoundation", "Cocoa", "Carbon", "IOKit"]
        elif self.settings.os == "Windows":
            self.cpp_info.system_libs = [
                "netapi32", "kernel32", "user32", "advapi32", "userenv","ws2_32", "gdi32",
                "comdlg32", "imm32", "comctl32", "shell32", "uuid", "ole32", "oleaut32"
            ]

        tk_library = os.path.join(self.package_folder, "lib", "{}{}".format(self.name, ".".join(self.version.split(".")[:2]))).replace("\\", "/")
        self.output.info("Setting TK_LIBRARY environment variable: {}".format(tk_library))
        self.env_info.TK_LIBRARY = tk_library

        tcl_root = self.package_folder.replace("\\", "/")
        self.output.info("Setting TCL_ROOT environment variable: {}".format(tcl_root))
        self.env_info.TCL_ROOT = tcl_root
