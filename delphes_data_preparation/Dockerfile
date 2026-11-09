FROM rootproject/root:6.34.00-ubuntu24.04@sha256:3b46b2e131ade9b2758f7e28cde783893c3ec376645763ebe415b7f97dad9aa6
USER root
RUN apt-get update && apt-get install -y --no-install-recommends build-essential zlib1g-dev dos2unix rsync python3 curl ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /opt/src
RUN curl --fail --location --retry 3 https://pythia.org/releases/pythia83/pythia8313.tgz -o pythia.tgz && echo 'd07e801501c4dcb76d948dc63285375f597453c1d6ec65e71287603dc776718c  pythia.tgz' | sha256sum -c - && tar xzf pythia.tgz && rm pythia.tgz
WORKDIR /opt/src/pythia8313
RUN ./configure --prefix=/opt/pythia8 && make -j4 && make install
ENV PYTHIA8=/opt/pythia8
WORKDIR /opt/src
RUN curl --fail --location --retry 3 https://github.com/delphes/delphes/archive/refs/tags/3.5.1.tar.gz -o delphes.tgz && echo 'b60d26d2ee2c84b58fbf2cf397fabd0ef3e89d3a0546d843c4ada82cc802d787  delphes.tgz' | sha256sum -c - && tar xzf delphes.tgz && mv delphes-3.5.1 /opt/Delphes && rm delphes.tgz
WORKDIR /opt/Delphes
RUN make HAS_PYTHIA8=true -j4 && printf '/opt/pythia8/lib\n' > /etc/ld.so.conf.d/pythia8.conf && ldconfig
CMD ["/bin/bash"]
