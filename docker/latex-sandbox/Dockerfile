FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    texlive-latex-base \
    texlive-latex-recommended \
    texlive-latex-extra \
    texlive-fonts-recommended \
    texlive-lang-cyrillic \
    texlive-science \
    latexmk \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --system --uid 10001 --create-home --home-dir /home/latex latex

WORKDIR /work
COPY docker/latex-sandbox/compile.sh /usr/local/bin/compile.sh
RUN chmod 0555 /usr/local/bin/compile.sh
USER 10001:10001
ENTRYPOINT ["/usr/local/bin/compile.sh"]
