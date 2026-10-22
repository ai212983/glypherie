FROM python:3.10-slim-bookworm@sha256:5be5aaecb962a41567bc8041f1e9e3432cb085b037fe057f9a562630b2e4b370
ENV DEBIAN_FRONTEND=noninteractive MPLBACKEND=Agg PYTHONDONTWRITEBYTECODE=1
RUN apt-get update && apt-get install -y --no-install-recommends \
      swig cmake g++ make pkg-config patch \
      libarmadillo-dev libopencv-dev \
      libboost-system-dev libboost-filesystem-dev \
      libcgal-dev libgmp-dev libmpfr-dev libboost-dev \
 && rm -rf /var/lib/apt/lists/*
COPY docker/requirements.txt /opt/requirements.txt
RUN pip install --no-cache-dir -r /opt/requirements.txt
COPY vendor/skgeom /opt/vendor/skgeom
COPY docker/patches /opt/patches
RUN cd /opt/vendor/skgeom && patch -p1 < /opt/patches/skgeom-pybind11.patch \
 && pip install --no-cache-dir pybind11==2.11.1 \
 && pip install --no-cache-dir --no-deps --no-build-isolation /opt/vendor/skgeom
COPY vendor /opt/vendor
COPY docker/patches /opt/patches
RUN cd /opt/vendor/cautograff \
 && patch -p1 < /opt/patches/cautograff-debian.patch \
 && cd py \
 && swig -w322,362,509,389,503,312 -python -c++ -extranative -fastproxy \
      -I./../src -I./opencv-swig -I/usr/include/opencv4 cautograff.i \
 && echo "void initializeSwig_cautograff() { SWIG_init(); }" >> cautograff_wrap.cxx \
 && echo "void initializeSwig_cautograff();" >> cautograff_wrap.h \
 && cp cautograff.py cautograff/cautograff.py \
 && mkdir -p build && cd build \
 && cmake .. -DCMAKE_BUILD_TYPE=Release \
 && make -j"$(nproc)"
COPY docker/runtime-requirements.txt /opt/runtime-requirements.txt
RUN pip install --no-cache-dir -r /opt/runtime-requirements.txt
ENV PYTHONPATH=/opt/vendor/strokestyles:/opt/vendor/autograff:/opt/vendor/csfs:/opt/vendor/cautograff/py
COPY docker/run_extract.py /opt/run_extract.py
WORKDIR /work
ENTRYPOINT ["python", "/opt/run_extract.py"]
