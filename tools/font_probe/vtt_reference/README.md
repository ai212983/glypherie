# Microsoft VTT reference runtime

`fpgmtmpl.txt`, `preptmpl.txt`, and `cvttmpl.txt` are unchanged UTF-16 files from
[Microsoft VisualTrueType](https://github.com/microsoft/VisualTrueType/tree/1bd4ed4383f8390b0140e05d330491fcadd3e8e0/templates),
commit `1bd4ed4383f8390b0140e05d330491fcadd3e8e0`. `LICENSE` is the upstream MIT license.

Install the compiler built from the same revision in the probe environment:

```sh
tools/font_probe/.venv/bin/python -m pip install 'vttcompilepy @ git+https://github.com/microsoft/VisualTrueType.git@1bd4ed4383f8390b0140e05d330491fcadd3e8e0'
```

This builds Microsoft's native compiler; it requires a working C++ toolchain.
The tested package reports version `0.0.1.13`. The Python wrapper is an experiment
dependency, separate from the reusable font generator.

See the [experiment and mapping contract](../../../docs/notes/vtt-compiler-diagonals.md)
for command selection, runtime limitations, and reproduction.
