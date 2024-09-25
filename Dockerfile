# This Dockerfile builds an image to run benchmark experiments in
# Copyright (c) 2023 Robert Bosch GmbH
# SPDX-License-Identifier: AGPL-3.0

FROM ubuntu:18.04
# Mimid's requirements are available for ubuntu 18, only

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y \
    openjdk-11-jdk-headless make graphviz graphviz-dev software-properties-common   git  \
    ninja-build subversion pkg-config  llvm-4.0 llvm-4.0-dev zlib1g-dev nano \
    libclang-8-dev clang-format-8 clang-8 clang-4.0 jq \
    autoconf dh-autoreconf automake libtool libjson-c-dev \
    wget build-essential checkinstall  liblzma-dev \
    libreadline-gplv2-dev libncursesw5-dev libssl-dev \
    libsqlite3-dev tk-dev libgdbm-dev libc6-dev libbz2-dev libffi-dev zlib1g-dev \
    python3-pip python3-venv python3-distutils python3-dev g++ python-dev autotools-dev libicu-dev libbz2-dev libboost-all-dev \
    python3-software-properties python3-apt texinfo libc6-dbg \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install a newer LibC :/
#RUN wget -c https://ftp.gnu.org/gnu/glibc/glibc-2.28.tar.gz && \
#    tar -zxvf glibc-2.28.tar.gz && \
#    mkdir glibc-2.28/build && \
#    cd glibc-2.28/build && \
#    ../configure --prefix=/usr && \
#    make && \
#    make install

# Unfortunately, we need specific versions of python and llvm for running Mimid that are not available anymore :(

#RUN add-apt-repository ppa:deadsnakes/ppa \
#    && apt-get update \
#    && DEBIAN_FRONTEND=noninteractive apt-get install -y \
#    python3.10 python3.10-distutils python3-venv python3-pip python3.10-dev \
#    python3-software-properties python3-apt

# Therefore we compile Python from scratch
RUN cd /opt && wget https://www.python.org/ftp/python/3.9.17/Python-3.9.17.tgz && tar xzf Python-3.9.17.tgz && cd Python-3.9.17 && ./configure --enable-optimizations && make altinstall

RUN update-alternatives --install /usr/bin/python3 python3 /opt/Python-3.9.17/python 2

RUN ln -s /usr/bin/clang-8 /usr/bin/clang
RUN pip3 install --upgrade pip setuptools
RUN python3 -m pip install wheel graphviz jupyter pudb astor clang==8.0.1 markdown fuzzingbook meson==0.46.1 \
    lark-parser tqdm pygdbmi networkx

RUN wget https://ftp.gnu.org/gnu/gdb/gdb-9.2.tar.gz && \
    tar -xf gdb-9.2.tar.gz && cd gdb-9.2 && mkdir build && cd build && \
    ../configure && make && make install
    

RUN wget https://sourceware.org/pub/valgrind/valgrind-3.21.0.tar.bz2 && \
    tar -xf valgrind-3.21.0.tar.bz2 && cd valgrind-3.21.0 && \
    ./configure && make && make install

RUN git clone https://github.com/json-c/json-c.git && cd json-c && \
    git checkout ee9f67c81a3c2a44557f0cc16dc136c140293252 && \
    sh autogen.sh && ./configure && make && make install
    
RUN wget https://github.com/Kitware/CMake/releases/download/v3.29.0-rc2/cmake-3.29.0-rc2-linux-x86_64.sh && \
    chmod a+x cmake-3.29.0-rc2-linux-x86_64.sh &&  bash cmake-3.29.0-rc2-linux-x86_64.sh --skip-license && \
    ln -s /opt/cmake-3.29.0-rc2-linux-x86_64/bin/ /usr/local/bin

# Compile static libxml
RUN git clone https://github.com/GNOME/libxml2.git && cd libxml2 && \
    git checkout v2.12.4 && mkdir build && cd build && \
    cmake -D LIBXML2_WITH_ZLIB=OFF -D LIBXML2_WITH_LZMA=OFF  -DLIBXML2_WITH_ICONV=OFF -DLIBXML2_WITH_THREADS=OFF -DBUILD_SHARED_LIBS=OFF -DCMAKE_BUILD_TYPE=Debug -DCMAKE_C_FLAGS="-O0" ..  && \
    make && make install && ldconfig
    
RUN wget --no-check-certificate https://boostorg.jfrog.io/artifactory/main/release/1.80.0/source/boost_1_80_0.tar.gz && \
    tar -xf boost_1_80_0.tar.gz && cd boost_1_80_0 && ./bootstrap.sh --prefix=/usr/local --with-toolset=gcc && \
    ./b2 toolset=gcc && ./b2 install

    
RUN git clone https://github.com/vrthra/mimid.git /mimid


RUN cd /mimid && tar -xf taints.tar.gz && cd taints && \
    meson build/debug --prefix="$(pwd)/install" && \
    ninja -C build/debug install

RUN sed -i 's+pfuzzer=../../taints+pfuzzer=../taints+g' /mimid/Cmimid/Makefile


RUN git clone https://github.com/neil-kulkarni/arvada.git /arvada

RUN git clone https://github.com/rifatarefin/treevada /treevada


RUN     mkdir /GDBMiner
COPY    src /GDBMiner/src
COPY    example_programs /example_programs

# Compile svgpp
#RUN cd example_programs/svgcpp/svgpp/src/demo/render/ && mkdir build && cd build && \
#    cmake -DCMAKE_BUILD_TYPE=Debug -DCMAKE_CXX_FLAGS="-O0 -DDEBUG" .. &&  make

 
    
COPY    fetch_example_programs.sh  .
RUN     chmod a+x fetch_example_programs.sh && ./fetch_example_programs.sh
COPY    setup.py /GDBMiner/
COPY    setup.cfg /GDBMiner/
RUN     python3 -m pip install -e /GDBMiner/

COPY    run_experiment.sh .
RUN     chmod a+x run_experiment.sh 


# Number of seeds to generate 
ENV     NUMBER_OF_SEEDS=20

#Whether we use the original mimid algorithm or our enhanced one
ENV     ORIGINAL_MIMID=0

#Whether we move watchpoints down the tree until we a new one occurs
ENV     DELAY_WP=0

#Number of inputs to sample for calculating precision and recall values
ENV     PRECISION_SET_SIZE=1000
