"""PlatformIO (pre-script): FPU de hardware (Cortex-M4F, FPv4-SP) en compilacion Y enlazado.

Con -mfloat-abi=hard solo en build_flags, el enlazado fallaba ("uses VFP register arguments, firmware.elf does
not"); aqui las banderas van a CCFLAGS y a LINKFLAGS. __FPU_USED lo define CMSIS al ver la ABI hard y
SystemInit() habilita CP10/CP11.
"""
Import("env")  # noqa: F821  (lo inyecta SCons)

flags = ["-mfpu=fpv4-sp-d16", "-mfloat-abi=hard"]
env.Append(CCFLAGS=flags, LINKFLAGS=flags)  # noqa: F821
