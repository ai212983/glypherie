#!/bin/sh
# Isolated build of the exact-topology reference checker.
#
#   sh experiments/hobby_fitting/exact_topology/build.sh
#
# Inputs: CGAL_DIR (optional; staged CGAL 6.1.1 cmake directory),
# CXX (optional; default clang++). Outputs the binary to
# out/diagnostics/direct-diagonal/exact-topology/bin/exact_topology.
# No system installs, no network, no Docker.
set -eu
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
root=$(CDPATH= cd -- "$here/../../.." && pwd)
bindir="$root/out/diagnostics/direct-diagonal/exact-topology/bin"
builddir="$root/out/diagnostics/direct-diagonal/exact-topology/build"
mkdir -p "$bindir" "$builddir"
cmake -S "$here" -B "$builddir" -DCMAKE_BUILD_TYPE=Release \
  ${CGAL_DIR:+-DCGAL_DIR="$CGAL_DIR"} \
  ${CMAKE_ARGS:-}
cmake --build "$builddir" --target exact_topology
cp "$builddir/exact_topology" "$bindir/exact_topology"
"$bindir/exact_topology" < /dev/null > /dev/null 2>&1 || true
echo "built $bindir/exact_topology"
