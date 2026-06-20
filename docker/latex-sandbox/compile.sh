#!/bin/sh
set -eu
MAIN_FILE="${1:-main.tex}"
export HOME=/tmp
export TEXMFOUTPUT=/work/out
export openin_any="${openin_any:-p}"
export openout_any="${openout_any:-p}"
export shell_escape=f
mkdir -p /work/out
pdflatex -no-shell-escape -interaction=nonstopmode -halt-on-error -file-line-error -output-directory=/work/out "$MAIN_FILE"
pdflatex -no-shell-escape -interaction=nonstopmode -halt-on-error -file-line-error -output-directory=/work/out "$MAIN_FILE"
