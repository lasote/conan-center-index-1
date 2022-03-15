import contextlib
import fnmatch
import json
import os
import shutil
import textwrap
from shutil import which

from conan import ConanFile
from conan.errors import ConanInvalidConfiguration
from conan.tools.build import cross_building
from conan.tools.env import Environment
from conan.tools.files import save, get, load, chdir, replace_in_file, rename, copy
from conan.tools.gnu import AutotoolsToolchain, AutotoolsDeps
from conan.tools.layout import basic_layout
from conan.tools.microsoft import unix_path, VCVars, is_msvc

required_conan_version = ">=1.43.0"


class OpenSSLConan(ConanFile):
    name = "openssl"
    settings = "os", "arch", "compiler", "build_type"
    url = "https://github.com/conan-io/conan-center-index"
    homepage = "https://github.com/openssl/openssl"
    license = "Apache-2.0"
    topics = ("openssl", "ssl", "tls", "encryption", "security")
    description = "A toolkit for the Transport Layer Security (TLS) and Secure Sockets Layer (SSL) protocols"
    options = {
        "shared": [True, False],
        "fPIC": [True, False],
        "enable_weak_ssl_ciphers": [True, False],
        "386": [True, False],
        "capieng_dialog": [True, False],
        "enable_capieng": [True, False],
        "no_aria": [True, False],
        "no_asm": [True, False],
        "no_async": [True, False],
        "no_blake2": [True, False],
        "no_bf": [True, False],
        "no_camellia": [True, False],
        "no_chacha": [True, False],
        "no_cms": [True, False],
        "no_comp": [True, False],
        "no_ct": [True, False],
        "no_cast": [True, False],
        "no_deprecated": [True, False],
        "no_des": [True, False],
        "no_dgram": [True, False],
        "no_dh": [True, False],
        "no_dsa": [True, False],
        "no_dso": [True, False],
        "no_ec": [True, False],
        "no_ecdh": [True, False],
        "no_ecdsa": [True, False],
        "no_engine": [True, False],
        "no_filenames": [True, False],
        "no_fips": [True, False],
        "no_gost": [True, False],
        "no_idea": [True, False],
        "no_legacy": [True, False],
        "no_md2": [True, False],
        "no_md4": [True, False],
        "no_mdc2": [True, False],
        "no_ocsp": [True, False],
        "no_pinshared": [True, False],
        "no_rc2": [True, False],
        "no_rc4": [True, False],
        "no_rc5": [True, False],
        "no_rfc3779": [True, False],
        "no_rmd160": [True, False],
        "no_sm2": [True, False],
        "no_sm3": [True, False],
        "no_sm4": [True, False],
        "no_srp": [True, False],
        "no_srtp": [True, False],
        "no_sse2": [True, False],
        "no_ssl": [True, False],
        "no_stdio": [True, False],
        "no_seed": [True, False],
        "no_sock": [True, False],
        "no_ssl3": [True, False],
        "no_threads": [True, False],
        "no_tls1": [True, False],
        "no_ts": [True, False],
        "no_whirlpool": [True, False],
        "no_zlib": [True, False],
        "openssldir": "ANY",
    }
    default_options = {key: False for key in options.keys()}
    default_options["fPIC"] = True
    default_options["openssldir"] = None

    exports_sources = "patches/*"

    def layout(self):
        basic_layout(self, src_folder="source")

    @property
    def _openssl_build_json_path(self):
        return os.path.join(self.generators_folder, "openssl_build.json")

    def generate(self):
        perl = "perl"
        if self.settings_build.os == "Windows" and not self.win_bash:
            # enforce strawberry perl, otherwise wrong perl could be used (from Git bash, MSYS, etc.)
            if "strawberryperl" in self.dependencies.items():
                perl = os.path.join(self.dependencies["strawberryperl"].bindirs[0], "perl.exe")

        configure_args = self._get_configure_args(perl)
        build_data = {"configure_args": configure_args, "perl_exe": perl}
        contents = json.dumps(build_data)
        save(self, self._openssl_build_json_path, contents)
        if self._use_nmake:
            VCVars(self).generate()

        # Environment adjustements
        env = Environment()
        if build_data.get("perl_exe"):
            env.define("PERL", build_data["perl_exe"])

        if self.settings.compiler == "apple-clang":
            sdk_path = self.conf.get("tools.apple:sdk_path")
            if sdk_path:
                env.define("CROSS_SDK", os.path.basename(sdk_path))
                env.define("CROSS_TOP", os.path.dirname(os.path.dirname(sdk_path)))
        envvars = env.vars(self)
        envvars.save_script("conanopensslbuild")

        # Create the "Configurations/20-conan.conf"
        self._create_targets()

        # Adjust runtime
        if self._use_nmake:
            self._replace_runtime_in_file(os.path.join(self.source_folder,
                                                       "Configurations", "10-main.conf"))
        # workaround for clang-cl not producing .pdb files
        if self._is_clangcl:
            save(self, os.path.join(self.source_folder, "ossl_static.pdb"), "")

    def config_options(self):
        try:
            if self.settings.os != "Windows":
                del self.options.capieng_dialog
                del self.options.enable_capieng
            else:
                del self.options.fPIC

            if self.settings.os == "Emscripten":
                self.options.no_asm = True
                self.options.no_threads = True
                self.options.no_stdio = True
        except Exception:
            pass

    def configure(self):
        try:
            if self.options.shared:
                del self.options.fPIC
            del self.settings.compiler.libcxx
            del self.settings.compiler.cppstd
        except Exception:
            pass

    def requirements(self):
        if not self.options.no_zlib:
            self.requires("zlib/1.2.11")

    def build_requirements(self):
        if self.settings_build.os == "Windows":
            if not self.win_bash:
                self.build_requires("strawberryperl/5.30.0.1")
            if not self.options.no_asm and not which("nasm"):
                self.build_requires("nasm/2.15.05")
        if self.win_bash:
            if not self.conf.get("tools.microsoft.bash:path"):
                self.build_requires("msys2/cci.latest")

    def validate(self):
        if self.settings.os == "Emscripten":
            if not all((self.options.no_asm, self.options.no_threads, self.options.no_stdio)):
                raise ConanInvalidConfiguration("os=Emscripten requires openssl:{no_asm,no_threads,no_stdio}=True")

    @property
    def _is_clangcl(self):
        return self.settings.compiler == "clang" and self.settings.os == "Windows"

    @property
    def _is_mingw(self):
        return self.settings.os == "Windows" and self.settings.compiler == "gcc"

    @property
    def _use_nmake(self):
        return self._is_clangcl or is_msvc(self)

    def source(self):
        get(self, **self.conan_data["sources"][self.version], strip_root=True)

    @property
    def _target(self):
        target = f"conan-{self.settings.build_type}-{self.settings.os}-{self.settings.arch}-{self.settings.compiler}-{self.settings.compiler.version}"
        if self._use_nmake:
            target = f"VC-{target}"  # VC- prefix is important as it's checked by Configure
        if self._is_mingw:
            target = f"mingw-{target}"
        return target

    @property
    def _perlasm_scheme(self):
        # right now, we need to tweak this for iOS & Android only, as they inherit from generic targets
        if self.settings.os in ("iOS", "watchOS", "tvOS"):
            return {
                "armv7": "ios32",
                "armv7s": "ios32",
                "armv8": "ios64",
                "armv8_32": "ios64",
                "armv8.3": "ios64",
                "armv7k": "ios32",
            }.get(str(self.settings.arch), None)
        elif self.settings.os == "Android":
            return {
                "armv7": "void",
                "armv8": "linux64",
                "mips": "o32",
                "mips64": "64",
                "x86": "android",
                "x86_64": "elf",
            }.get(str(self.settings.arch), None)
        return None

    @property
    def _asm_target(self):
        if self.settings.os in ("Android", "iOS", "watchOS", "tvOS"):
            return {
                "x86": "x86_asm" if self.settings.os == "Android" else None,
                "x86_64": "x86_64_asm" if self.settings.os == "Android" else None,
                "armv5el": "armv4_asm",
                "armv5hf": "armv4_asm",
                "armv6": "armv4_asm",
                "armv7": "armv4_asm",
                "armv7hf": "armv4_asm",
                "armv7s": "armv4_asm",
                "armv7k": "armv4_asm",
                "armv8": "aarch64_asm",
                "armv8_32": "aarch64_asm",
                "armv8.3": "aarch64_asm",
                "mips": "mips32_asm",
                "mips64": "mips64_asm",
                "sparc": "sparcv8_asm",
                "sparcv9": "sparcv9_asm",
                "ia64": "ia64_asm",
                "ppc32be": "ppc32_asm",
                "ppc32": "ppc32_asm",
                "ppc64le": "ppc64_asm",
                "ppc64": "ppc64_asm",
                "s390": "s390x_asm",
                "s390x": "s390x_asm"
            }.get(str(self.settings.os), None)

    @property
    def _targets(self):
        is_cygwin = self.settings.get_safe("os.subsystem") == "cygwin"
        return {
            "Linux-x86-clang": "linux-x86-clang",
            "Linux-x86_64-clang": "linux-x86_64-clang",
            "Linux-x86-*": "linux-x86",
            "Linux-x86_64-*": "linux-x86_64",
            "Linux-armv4-*": "linux-armv4",
            "Linux-armv4i-*": "linux-armv4",
            "Linux-armv5el-*": "linux-armv4",
            "Linux-armv5hf-*": "linux-armv4",
            "Linux-armv6-*": "linux-armv4",
            "Linux-armv7-*": "linux-armv4",
            "Linux-armv7hf-*": "linux-armv4",
            "Linux-armv7s-*": "linux-armv4",
            "Linux-armv7k-*": "linux-armv4",
            "Linux-armv8-*": "linux-aarch64",
            "Linux-armv8.3-*": "linux-aarch64",
            "Linux-armv8-32-*": "linux-arm64ilp32",
            "Linux-mips-*": "linux-mips32",
            "Linux-mips64-*": "linux-mips64",
            "Linux-ppc32-*": "linux-ppc32",
            "Linux-ppc32le-*": "linux-pcc32",
            "Linux-ppc32be-*": "linux-ppc32",
            "Linux-ppc64-*": "linux-ppc64",
            "Linux-ppc64le-*": "linux-ppc64le",
            "Linux-pcc64be-*": "linux-pcc64",
            "Linux-s390x-*": "linux64-s390x",
            "Linux-e2k-*": "linux-generic64",
            "Linux-sparc-*": "linux-sparcv8",
            "Linux-sparcv9-*": "linux64-sparcv9",
            "Linux-*-*": "linux-generic32",
            "Macos-x86-*": "darwin-i386-cc",
            "Macos-x86_64-*": "darwin64-x86_64-cc",
            "Macos-ppc32-*": "darwin-ppc-cc",
            "Macos-ppc32be-*": "darwin-ppc-cc",
            "Macos-ppc64-*": "darwin64-ppc-cc",
            "Macos-ppc64be-*": "darwin64-ppc-cc",
            "Macos-armv8-*": "darwin64-arm64-cc",
            "Macos-*-*": "darwin-common",
            "iOS-x86_64-*": "darwin64-x86_64-cc",
            "iOS-*-*": "iphoneos-cross",
            "watchOS-*-*": "iphoneos-cross",
            "tvOS-*-*": "iphoneos-cross",
            # Android targets are very broken, see https://github.com/openssl/openssl/issues/7398
            "Android-armv7-*": "linux-generic32",
            "Android-armv7hf-*": "linux-generic32",
            "Android-armv8-*": "linux-generic64",
            "Android-x86-*": "linux-x86-clang",
            "Android-x86_64-*": "linux-x86_64-clang",
            "Android-mips-*": "linux-generic32",
            "Android-mips64-*": "linux-generic64",
            "Android-*-*": "linux-generic32",
            "Windows-x86-gcc": "Cygwin-x86" if is_cygwin else "mingw",
            "Windows-x86_64-gcc": "Cygwin-x86_64" if is_cygwin else "mingw64",
            "Windows-*-gcc": "Cygwin-common" if is_cygwin else "mingw-common",
            "Windows-ia64-Visual Studio": "VC-WIN64I",  # Itanium
            "Windows-x86-Visual Studio": "VC-WIN32",
            "Windows-x86_64-Visual Studio": "VC-WIN64A",
            "Windows-armv7-Visual Studio": "VC-WIN32-ARM",
            "Windows-armv8-Visual Studio": "VC-WIN64-ARM",
            "Windows-*-Visual Studio": "VC-noCE-common",
            "Windows-ia64-clang": "VC-WIN64I",  # Itanium
            "Windows-x86-clang": "VC-WIN32",
            "Windows-x86_64-clang": "VC-WIN64A",
            "Windows-armv7-clang": "VC-WIN32-ARM",
            "Windows-armv8-clang": "VC-WIN64-ARM",
            "Windows-*-clang": "VC-noCE-common",
            "WindowsStore-x86-*": "VC-WIN32-UWP",
            "WindowsStore-x86_64-*": "VC-WIN64A-UWP",
            "WindowsStore-armv7-*": "VC-WIN32-ARM-UWP",
            "WindowsStore-armv8-*": "VC-WIN64-ARM-UWP",
            "WindowsStore-*-*": "VC-WIN32-ONECORE",
            "WindowsCE-*-*": "VC-CE",
            "SunOS-x86-gcc": "solaris-x86-gcc",
            "SunOS-x86_64-gcc": "solaris64-x86_64-gcc",
            "SunOS-sparc-gcc": "solaris-sparcv8-gcc",
            "SunOS-sparcv9-gcc": "solaris64-sparcv9-gcc",
            "SunOS-x86-suncc": "solaris-x86-cc",
            "SunOS-x86_64-suncc": "solaris64-x86_64-cc",
            "SunOS-sparc-suncc": "solaris-sparcv8-cc",
            "SunOS-sparcv9-suncc": "solaris64-sparcv9-cc",
            "SunOS-*-*": "solaris-common",
            "*BSD-x86-*": "BSD-x86",
            "*BSD-x86_64-*": "BSD-x86_64",
            "*BSD-ia64-*": "BSD-ia64",
            "*BSD-sparc-*": "BSD-sparcv8",
            "*BSD-sparcv9-*": "BSD-sparcv9",
            "*BSD-armv8-*": "BSD-generic64",
            "*BSD-mips64-*": "BSD-generic64",
            "*BSD-ppc64-*": "BSD-generic64",
            "*BSD-ppc64le-*": "BSD-generic64",
            "*BSD-ppc64be-*": "BSD-generic64",
            "AIX-ppc32-gcc": "aix-gcc",
            "AIX-ppc64-gcc": "aix64-gcc",
            "AIX-pcc32-*": "aix-cc",
            "AIX-ppc64-*": "aix64-cc",
            "AIX-*-*": "aix-common",
            "*BSD-*-*": "BSD-generic32",
            "Emscripten-*-*": "cc",
            "Neutrino-*-*": "BASE_unix",
        }

    @property
    def _ancestor_target(self):
        if self.conf.get("user.openssl.configuration"):
            return self.conf.get("user.openssl.configuration")
        compiler = "Visual Studio" if self.settings.compiler == "msvc" else self.settings.compiler
        query = f"{self.settings.os}-{self.settings.arch}-{compiler}"
        ancestor = next((self._targets[i] for i in self._targets if fnmatch.fnmatch(query, i)), None)
        if not ancestor:
            raise ConanInvalidConfiguration(
                f"Unsupported configuration ({self.settings.os}/{self.settings.arch}/{self.settings.compiler}).\n"
                f"Please open an issue at {self.url}.\n"
                f"Alternatively, set the CONAN_OPENSSL_CONFIGURATION environment variable into your conan profile."
            )
        return ancestor

    def _tool(self, env_name, apple_name):
        if env_name in os.environ:
            return os.environ[env_name]
        if self.settings.compiler == "apple-clang":
            # FIXME: XCRun not supported
            # return getattr(tools.XCRun(self.settings), apple_name)
            return apple_name
        return None

    def _get_default_openssl_dir(self):
        if self.settings.os == "Linux":
            return "/etc/ssl"
        return os.path.join(self.package_folder or ".", "res")

    def _get_configure_args(self, perl):
        openssldir = self.options.openssldir or self._get_default_openssl_dir()
        dest_folder = self.package_folder or self.build_folder
        prefix = unix_path(self, dest_folder) if self.win_bash else dest_folder
        openssldir = unix_path(self, openssldir) if self.win_bash else openssldir
        args = [
            '"%s"' % (self._target),
            "shared" if self.options.shared else "no-shared",
            "--prefix=\"%s\"" % prefix,
            "--libdir=lib",
            "--openssldir=\"%s\"" % openssldir,
            "no-unit-test",
            "no-threads" if self.options.no_threads else "threads",
            "PERL=%s" % perl,
            "no-tests",
            "--debug" if self.settings.build_type == "Debug" else "--release",
        ]

        if self.settings.os == "Android":
            args.append(" -D__ANDROID_API__=%s" % str(self.settings.os.api_level))  # see NOTES.ANDROID
        if self.settings.os == "Emscripten":
            args.append("-D__STDC_NO_ATOMICS__=1")
        if self.settings.os == "Windows":
            if self.options.enable_capieng:
                args.append("enable-capieng")
            if self.options.capieng_dialog:
                args.append("-DOPENSSL_CAPIENG_DIALOG=1")
        else:
            args.append("-fPIC" if self.options.get_safe("fPIC", True) else "no-pic")

        args.append("no-fips" if self.options.get_safe("no_fips", True) else "enable-fips")

        if self.settings.os == "Neutrino":
            args.append("no-asm -lsocket -latomic")

        if not self.options.no_zlib:
            zlib_info = self.dependencies["zlib"].cpp_info
            include_path = zlib_info.includedirs[0]
            if self.settings.os == "Windows":
                lib_path = "%s/%s.lib" % (zlib_info.libdirs[0], zlib_info.libs[0])
            else:
                # Just path, linux will find the right file
                lib_path = zlib_info.libdirs[0]
            if self.settings_build.os == "Windows":
                # clang-cl doesn't like backslashes in #define CFLAGS (builldinf.h -> cversion.c)
                include_path = include_path.replace("\\", "/")
                lib_path = lib_path.replace("\\", "/")

            if self.dependencies["zlib"].options.get_safe("shared"):
                args.append("zlib-dynamic")
            else:
                args.append("zlib")

            args.extend([
                '--with-zlib-include="%s"' % include_path,
                '--with-zlib-lib="%s"' % lib_path
            ])
        for option_name, value in self.options.items():
            if self.options.get_safe(option_name, False) and option_name not in ("shared", "fPIC", "openssldir", "capieng_dialog", "enable_capieng", "zlib", "no_fips"):
                self.output.info(f"Activated option: {option_name}")
                args.append(option_name.replace("_", "-"))
        return args

    def _create_targets(self):
        config_template = textwrap.dedent("""\
            {targets} = (
                "{target}" => {{
                    inherit_from => {ancestor},
                    cflags => add("{cflags}"),
                    cxxflags => add("{cxxflags}"),
                    {defines}
                    includes => add({includes}),
                    lflags => add("{lflags}"),
                    {shared_target}
                    {shared_cflag}
                    {shared_extension}
                    {cc}
                    {cxx}
                    {ar}
                    {ranlib}
                    {perlasm_scheme}
                }},
            );
        """)

        toolchain = AutotoolsToolchain(self)
        deps = AutotoolsDeps(self)
        env = toolchain.environment().compose_env(deps.environment)
        vars = env.vars(self)
        cflags = vars.get("CFLAGS")
        cxxflags = vars.get("CXXFLAGS")

        cc = self._tool("CC", "cc")
        cxx = self._tool("CXX", "cxx")
        ar = self._tool("AR", "ar")
        ranlib = self._tool("RANLIB", "ranlib")

        perlasm_scheme = ""
        if self._perlasm_scheme:
            perlasm_scheme = 'perlasm_scheme => "%s",' % self._perlasm_scheme

        cc = 'cc => "%s",' % cc if cc else ""
        cxx = 'cxx => "%s",' % cxx if cxx else ""
        ar = 'ar => "%s",' % ar if ar else ""
        defines = " ".join(toolchain.defines)
        defines = 'defines => add("%s"),' % defines if defines else ""
        ranlib = 'ranlib => "%s",' % ranlib if ranlib else ""
        targets = "my %targets"

        includes = ""
        if not self.options.no_zlib:
            includes = ", ".join(['"%s"' % include for include in self.dependencies["zlib"].cpp_info.includedirs])
        if self.settings.os == "Windows":
            includes = includes.replace("\\", "/")  # OpenSSL doesn't like backslashes

        if self._asm_target:
            ancestor = '[ "%s", asm("%s") ]' % (self._ancestor_target, self._asm_target)
        else:
            ancestor = '[ "%s" ]' % self._ancestor_target
        shared_cflag = ""
        shared_extension = ""
        shared_target = ""
        if self.settings.os == "Neutrino":
            if self.options.shared:
                shared_extension = 'shared_extension => ".so.\$(SHLIB_VERSION_NUMBER)",'
                shared_target = 'shared_target  => "gnu-shared",'
            if self.options.get_safe("fPIC", True):
                shared_cflag = 'shared_cflag => "-fPIC",'

        config = config_template.format(
            targets=targets,
            target=self._target,
            ancestor=ancestor,
            cc=cc,
            cxx=cxx,
            ar=ar,
            ranlib=ranlib,
            cflags=cflags,
            cxxflags=cxxflags,
            defines=defines,
            includes=includes,
            perlasm_scheme=perlasm_scheme,
            shared_target=shared_target,
            shared_extension=shared_extension,
            shared_cflag=shared_cflag,
            lflags=" ".join(toolchain.ldflags)
        )
        self.output.info("using target: %s -> %s" % (self._target, self._ancestor_target))
        self.output.info(config)

        save(self, os.path.join(self.source_folder, "Configurations", "20-conan.conf"), config)

    def _run_make(self, targets=None, makefile=None, parallel=True):
        command = [self._make_program]
        if makefile:
            command.extend(["-f", makefile])
        if targets:
            command.extend(targets)
        if not self._use_nmake:
            command.append(("-j%s" % self.conf.get("tools.build:jobs", 1)) if parallel else "-j1")
        self.run(" ".join(command))

    @property
    def _make_nmake_makefile(self):
        return r"ms\ntdll.mak" if self.options.shared else r"ms\nt.mak"

    def _configure(self):
        data = json.loads(load(self, self._openssl_build_json_path))
        args = " ".join(data["configure_args"])
        with chdir(self, self.source_folder):
            self.run("{perl} ./Configure {args}".format(perl=data["perl_exe"], args=args))

    def _make(self):
        with chdir(self, self.source_folder):
            self._run_make()

    def _make_install(self):
        with chdir(self, self.source_folder):
            # workaround for MinGW (https://github.com/openssl/openssl/issues/7653)
            if not os.path.isdir(os.path.join(self.package_folder, "bin")):
                os.makedirs(os.path.join(self.package_folder, "bin"))

            self._run_make(targets=["install_sw"], parallel=False)

    @property
    def _cc(self):
        if "CROSS_COMPILE" in os.environ:
            return "gcc"
        if "CC" in os.environ:
            return os.environ["CC"]
        if self.settings.compiler == "apple-clang":
            #return tools.XCRun(self.settings).find("clang")
            # FIXME: Not support of XCRUN
            return "clang"
        elif self.settings.compiler == "clang":
            return "clang"
        elif self.settings.compiler == "gcc":
            return "gcc"
        return "cc"

    @contextlib.contextmanager
    def _make_context(self):
        # TODO: Not supported, the environment is applied with the 2.0 env launchers
        return
        if self._use_nmake:
            # Windows: when cmake generates its cache, it populates some environment variables as well.
            # If cmake also initiates openssl build, their values (containing spaces and forward slashes)
            # break nmake (don't know about mingw make). So we fix them
            def sanitize_env_var(var):
                return '"{}"'.format(var).replace('/', '\\') if '"' not in var else var
            env = {key: sanitize_env_var(tools.get_env(key)) for key in ("CC", "RC") if tools.get_env(key)}
            with tools.environment_append(env):
                yield
        else:
            yield

    def build(self):
        self._configure()
        # with self._make_context():
        self._make()

    @property
    def win_bash(self):
        return self.settings_build.os == "Windows" and not self._use_nmake and \
            (self._is_mingw or cross_building(self, skip_x64_x86=True))

    @property
    def _make_program(self):
        if self._use_nmake:
            return "nmake"
        make_program = self.conf.get("tools.gnu:make_program")
        if not make_program:
            raise Exception('could not find "make" executable. please set "tools.gnu:make_program" config')
        # FIXME: Not ready for the subsystem, unix_path to be used
        make_program = unix_path(self, make_program)
        return make_program

    @property
    def _runtime(self):
        if self.settings.compiler == "msvc":
            return "M{}{}".format(
                    "T" if self.settings.compiler.runtime == "static" else "D",
                    "d" if self.settings.compiler.runtime_type == "Debug" else "",
                )
        else:
            return self.settings.compiler.runtime

    def _replace_runtime_in_file(self, filename):
        for e in ("MDd", "MTd", "MD", "MT"):
            replace_in_file(self, filename, "/%s " % e, "/%s " % self._runtime, strict=False)
            replace_in_file(self, filename, "/%s\"" % e, "/%s\"" % self._runtime, strict=False)

    def package(self):
        copy(self, "*LICENSE*", self.source_folder, os.path.join(self.package_folder, "licenses"))
        self._make_install()
        for root, _, files in os.walk(self.package_folder):
            for filename in files:
                if fnmatch.fnmatch(filename, "*.pdb"):
                    os.unlink(os.path.join(self.package_folder, root, filename))
        if self._use_nmake:
            if self.settings.build_type == "Debug":
                with chdir(self, os.path.join(self.package_folder, "lib")):
                    rename(self, "libssl.lib", "libssld.lib")
                    rename(self, "libcrypto.lib", "libcryptod.lib")

        if self.options.shared:
            libdir = os.path.join(self.package_folder, "lib")
            for file in os.listdir(libdir):
                if self._is_mingw and file.endswith(".dll.a"):
                    continue
                if file.endswith(".a"):
                    os.unlink(os.path.join(libdir, file))

        if not self.options.no_fips:
            provdir = os.path.join(self.source_folder, "providers")
            if self.settings.os == "Macos":
                copy(self, "fips.dylib", provdir, os.path.join(self.package_folder, "lib/ossl-modules"))
            elif self.settings.os == "Windows":
                copy(self, "fips.dll", provdir, os.path.join(self.package_folder, "lib/ossl-modules"))
            else:
                copy(self, "fips.so", provdir, os.path.join(self.package_folder, "lib/ossl-modules"))

        try:
            shutil.rmtree(os.path.join(self.package_folder, "lib", "pkgconfig"))
        except FileNotFoundError:
            pass

        self._create_cmake_module_variables(
            os.path.join(self.package_folder, self._module_file_rel_path)
        )

    def _create_cmake_module_variables(self, module_file):
        content = textwrap.dedent("""\
            if(DEFINED OpenSSL_FOUND)
                set(OPENSSL_FOUND ${OpenSSL_FOUND})
            endif()
            if(DEFINED OpenSSL_INCLUDE_DIR)
                set(OPENSSL_INCLUDE_DIR ${OpenSSL_INCLUDE_DIR})
            endif()
            if(DEFINED OpenSSL_Crypto_LIBS)
                set(OPENSSL_CRYPTO_LIBRARY ${OpenSSL_Crypto_LIBS})
                set(OPENSSL_CRYPTO_LIBRARIES ${OpenSSL_Crypto_LIBS}
                                             ${OpenSSL_Crypto_DEPENDENCIES}
                                             ${OpenSSL_Crypto_FRAMEWORKS}
                                             ${OpenSSL_Crypto_SYSTEM_LIBS})
            endif()
            if(DEFINED OpenSSL_SSL_LIBS)
                set(OPENSSL_SSL_LIBRARY ${OpenSSL_SSL_LIBS})
                set(OPENSSL_SSL_LIBRARIES ${OpenSSL_SSL_LIBS}
                                          ${OpenSSL_SSL_DEPENDENCIES}
                                          ${OpenSSL_SSL_FRAMEWORKS}
                                          ${OpenSSL_SSL_SYSTEM_LIBS})
            endif()
            if(DEFINED OpenSSL_LIBRARIES)
                set(OPENSSL_LIBRARIES ${OpenSSL_LIBRARIES})
            endif()
            if(DEFINED OpenSSL_VERSION)
                set(OPENSSL_VERSION ${OpenSSL_VERSION})
            endif()
        """)
        save(self, module_file, content)

    @property
    def _module_subfolder(self):
        return os.path.join("lib", "cmake")

    @property
    def _module_file_rel_path(self):
        return os.path.join(self._module_subfolder,
                            "conan-official-{}-variables.cmake".format(self.name))

    def package_info(self):
        self.cpp_info.set_property("cmake_file_name", "OpenSSL")
        self.cpp_info.set_property("cmake_find_mode", "both")
        self.cpp_info.set_property("pkg_config_name", "openssl")
        self.cpp_info.components["ssl"].builddirs.append(self._module_subfolder)
        self.cpp_info.components["ssl"].set_property("cmake_build_modules", [self._module_file_rel_path])
        self.cpp_info.components["crypto"].builddirs.append(self._module_subfolder)
        self.cpp_info.components["crypto"].set_property("cmake_build_modules", [self._module_file_rel_path])
        # The components don't have default directories for anything, has to be declared
        self.cpp_info.components["ssl"].libdirs = ["lib"]
        self.cpp_info.components["crypto"].libdirs = ["lib"]
        self.cpp_info.components["ssl"].includedirs = ["include"]
        self.cpp_info.components["crypto"].includedirs = ["include"]

        if self._use_nmake:
            libsuffix = "d" if self.settings.build_type == "Debug" else ""
            self.cpp_info.components["ssl"].libs = ["libssl" + libsuffix]
            self.cpp_info.components["crypto"].libs = ["libcrypto" + libsuffix]
        else:
            self.cpp_info.components["ssl"].libs = ["ssl"]
            self.cpp_info.components["crypto"].libs = ["crypto"]

        self.cpp_info.components["ssl"].requires = ["crypto"]

        if not self.options.no_zlib:
            self.cpp_info.components["crypto"].requires.append("zlib::zlib")

        if self.settings.os == "Windows":
            self.cpp_info.components["crypto"].system_libs.extend(["crypt32", "ws2_32", "advapi32", "user32"])
        elif self.settings.os == "Linux":
            self.cpp_info.components["crypto"].system_libs.extend(["dl", "rt"])
            self.cpp_info.components["ssl"].system_libs.append("dl")
            if not self.options.no_threads:
                self.cpp_info.components["crypto"].system_libs.append("pthread")
                self.cpp_info.components["ssl"].system_libs.append("pthread")
        elif self.settings.os == "Neutrino":
            self.cpp_info.components["crypto"].system_libs.append("atomic")
            self.cpp_info.components["ssl"].system_libs.append("atomic")

        self.cpp_info.components["crypto"].set_property("cmake_target_name", "OpenSSL::Crypto")
        self.cpp_info.components["crypto"].set_property("pkg_config_name", "libcrypto")
        self.cpp_info.components["ssl"].set_property("cmake_target_name", "OpenSSL::SSL")
        self.cpp_info.components["ssl"].set_property("pkg_config_name", "libssl")
