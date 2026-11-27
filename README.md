# P-Gure

[한국어](README.kr.md)

P-Gure aims to provide a reusable Python library for drawing peer-to-peer
(P2P) network topologies and illustrating how protocols behave on them.
It is intended for researchers preparing figures for papers and presentations.

The design goal is to let researchers define peers and links once in
Python, then reuse that topology across figures. Keeping node positions
and visual conventions consistent makes it easier for readers to compare
message paths, peer roles, and network states.

Describe the peers, links, and message paths in YAML, then load and save the figure.

```python
from pgure import load, save_figure

save_figure(load("docs/gossip.yaml"), "gossip.svg")
```

Browse the [example gallery](examples/README.md) for YAML and figures covering
tree broadcasts, token rings, block exchanges, and bridged clusters.

For PNG, JPEG, or WebP,
install the raster extra with `python -m pip install -e '.[raster]'` and use
the desired filename extension. See the [YAML figure guide](docs/figure-yaml.md).

## Local development

With Python 3.10 or later, run these commands from the repository root
in an active virtual environment. An editable install makes changes in
`src/pgure/` available the next time you import the package.

```sh
python -m pip install -e .
python -c "import pgure"
```
