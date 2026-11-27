# P-Gure YAML figure format

A UTF-8 YAML document describes one topology. Each view adds a panel that shares the same peers, links, and coordinates. Write the data in a `.yaml` or `.yml` file, or pass the equivalent Python mapping to `from_dict`.

## One topology, two routes

![Two panels show the same four peers. The solid route goes through B and the dashed route through C.](gossip.svg)

The four links are available in both panels. A message's `path` lists the peers it visits in transmission order. The topology assigns the classes `eager` and `lazy` to the two routes. The companion stylesheet makes the lazy route dashed. [Topology](gossip.yaml) · [Stylesheet](gossip.meta.yaml)

```yaml
name: Gossip
peers:
  - {id: A, role: source}
  - {id: B, role: relay}
  - {id: C, role: relay}
  - {id: D, role: destination}

links:
  - {source: A, target: B}
  - {source: A, target: C}
  - {source: B, target: D}
  - {source: C, target: D}

views:
  - title: Via B
    messages:
      - {path: [A, B, D], kind: eager}
  - title: Via C
    messages:
      - {path: [A, C, D], kind: lazy}
```

From the repository root, render this example with the following Python.

```python
from pgure import load, save_figure

gossip = load("docs/gossip.yaml")
save_figure(gossip, "gossip.svg")
```

## Fields

| Field | Type | Meaning |
| --- | --- | --- |
| `name` | String, required | Topology identifier and default panel title. |
| `peers` | List of mappings | Each entry has an `id` and an optional `role`. Declare isolated peers here. Link endpoints also declare peers. |
| `links` | List of mappings | Each link has a `source` and `target`. Set `directed: true` for a one-way link. The default is undirected. The optional `kind` selects a link class. |
| `views` | List of mappings | Each view has a string `title` and an optional list of `messages`. Panels appear in list order. Titles may repeat. |
| `messages` entry | Mapping | A `path` of at least two peer IDs is required. Optional fields are `kind` for the message class and `placement` for its position relative to each link. |

Identifiers, roles, and classes are nonempty printable strings without whitespace. Quote IDs such as `"42"` and `"true"` so YAML reads them as strings. Titles may contain spaces and Unicode text. Use a YAML boolean for `directed`. Field order within mappings is free. Omitted lists default to empty lists.

A topology needs at least one peer. Repeated declarations of a peer or link refer to the same object. Conflicting roles or link classes, self-links, and overlapping directed and undirected links produce errors. Two opposite directed links can have different classes. Each hop in a message must follow a declared link in its transmission direction.

With no views, P-Gure draws the base topology in one panel. With no messages, a view shows the base topology alone. For a fan-out from A to B and C, list two messages with paths `[A, B]` and `[A, C]`. The single path `[A, B, C]` describes B forwarding to C. Messages in one panel have no implied timing relationship.

## Reading and validating data

Use `load(path)` for a file, `parse(text)` for a YAML string, and `from_dict(data)` for data already assembled by an experiment. All three return the same `Topology` that you can build with `add_peer`, `add_link`, `set_role`, and `add_view`.

```python
from pgure import from_dict

network = from_dict({
    "name": "Exchange",
    "links": [{"source": "client-1", "target": "server-1", "directed": True}],
    "views": [{"title": "Request", "messages": [{"path": ["client-1", "server-1"]}]}],
})
```

Invalid input raises `FigureError`. A data error identifies the field, such as `views[0].messages[1].path[0]` for a failed hop in the second message. YAML diagnostics include the source name and the line and column when available. Unknown fields and duplicate YAML keys are errors.

## Layout and style

The renderer places each connected component in breadth-first columns from its alphabetically first peer. It computes the layout once for all panels. An open arrowhead shows link direction and a filled arrowhead shows message direction.

![The same route drawn on the links in the left panel and outside them in the right panel.](message-placement.svg)

Set `placement: overlay` on a message to follow the link centerline, or `placement: outside` to draw a separate arc between the same peers. Placement applies to every hop of that message. Within each view, the first use of a link takes the centerline by default and additional uses go outside. An explicit overlay reserves the centerline even if it occurs later. An explicit outside arc leaves the centerline available. On straight links the arc bends away from the layout center, or to the right of travel when the center lies on the link axis. On curved links it follows the existing bend. [Download the placement comparison](message-placement.yaml).

### Companion stylesheets

Place `network.meta.yaml` beside `network.yaml` or `network.yml`. Each call to `load` reads the topology and its companion, so reloading after a design edit updates the next render. SVG, PNG, JPEG, and WebP exports all use the resulting style. A topology without a companion uses the built-in appearance.

```yaml
peers:
  default: {fill: white, stroke: "#253544", width: 1.5}
  roles:
    source: {fill: "#173e54", label_color: white}
links:
  default: {color: "#778794", line: solid}
  kinds:
    bridge: {line: "--", width: 2}
messages:
  kinds:
    lazy: {color: "#995321", line: dotted}
```

Rules inherit individual properties. Built-in values apply first, then the category's `default`, then the matching peer role or link/message kind. In the example, a bridge inherits the default link color and overrides its line pattern and width. Untagged objects and unmatched names use the category default. Each section is optional.

| Section | Select by | Properties |
| --- | --- | --- |
| `peers` | `roles` | `fill` for the interior, `stroke` for the border color, `width` and `line` for the border, `label_color` for the peer ID |
| `links` | `kinds` | `color`, `width`, `line` |
| `messages` | `kinds` | `color`, `width`, `line` |

Use SVG color strings and quote hex colors so YAML preserves the leading `#`. Widths are nonnegative numbers in SVG units. The named line patterns are `solid`, `dashed`, `dotted`, and `dash-dot`. Their short forms are `"-"`, `"--"`, `":"`, and `"-."`. For a custom pattern, use a sequence such as `line: [8, 3, 2, 3]` to alternate painted and empty lengths.

To share one stylesheet across files, use `load("network.yaml", meta="themes/paper.meta.yaml")`. An explicit path selects that stylesheet in place of the companion. For a topology constructed in memory, pass `load_style("themes/paper.meta.yaml")` as the `style` argument to `render_svg` or `save_figure`. An explicit `style` argument takes precedence for that render.

## Saving a figure

`save_figure` chooses the format from the filename extension and returns the output path. SVG export is included in the base package. For PNG, JPEG (`.jpg` or `.jpeg`), and lossless WebP, install the raster extra from the repository root.

```sh
python -m pip install -e '.[raster]'
```

```python
save_figure(gossip, "gossip.png", scale=2)
save_figure(gossip, "gossip.jpg", scale=2)
save_figure(gossip, "gossip.webp", scale=2)
```

The Gossip example measures 624 × 188 pixels at its default size and 1248 × 376 at `scale=2`. Use `render_svg(graph)` to get SVG markup as a Python string.
