# P-Gure

[한국어](README.kr.md)

P-Gure aims to provide a reusable Python library for drawing peer-to-peer
(P2P) network topologies and illustrating how protocols behave on them.
It is intended for researchers preparing figures for papers and presentations.

The design goal is to let researchers define peers and links once in
Python, then reuse that topology across figures. Keeping node positions
and visual conventions consistent makes it easier for readers to compare
message paths, peer roles, and network states.

Save figures with `save_figure(topology, "figure.svg")`. For PNG, JPEG, or WebP,
install the raster extra with `python -m pip install -e '.[raster]'` and use
the desired filename extension. See the [figure language guide](docs/figure-dsl.md#saving-a-figure).

## Local development

With Python 3.10 or later, run these commands from the repository root
in an active virtual environment. An editable install makes changes in
`src/pgure/` available the next time you import the package.

```sh
python -m pip install -e .
python -c "import pgure"
```
