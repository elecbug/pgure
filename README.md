# P-Gure

[한국어](README.kr.md)

P-Gure aims to provide a reusable Python library for drawing peer-to-peer
(P2P) network topologies and illustrating how protocols behave on them.
It is intended for researchers preparing figures for papers and presentations.

The design goal is to let researchers define peers and links once in
Python, then reuse that topology across figures. Keeping node positions
and visual conventions consistent makes it easier for readers to compare
message paths, peer roles, and network states.

Describe the peers, links, and message paths in YAML. Put colors, widths, line
patterns, and arrow placement in a companion file such as `gossip.meta.yaml`.
Loading the figure applies the stylesheet.

```python
from pgure import load, save_figure

save_figure(load("docs/gossip.yaml"), "gossip.svg")
```

Generate a network from a node count and a seed, or combine several groups
in one figure. Each group chooses its own model and parameters, such as ER
with edge probability `p` or WS with neighborhood size `k` and rewiring
probability `beta`. The stylesheet controls how peers and groups are arranged.
[Example gallery](examples/README.md) · [Seeded ER and WS example](examples/generated-groups.yaml)

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
