cmake_minimum_required(VERSION 3.20)
project(hobby_exact_topology CXX)

# Pinned reference revision: CGAL 6.1.1, exact source tarball staged
# by the parent worker. CGAL_DIR points at the staged lib/cmake/CGAL
# directory when it is not on the default search path.
find_package(CGAL 6.1.1 EXACT REQUIRED)

add_executable(exact_topology checker.cpp)
target_compile_features(exact_topology PRIVATE cxx_std_17)
target_link_libraries(exact_topology PRIVATE CGAL::CGAL)
