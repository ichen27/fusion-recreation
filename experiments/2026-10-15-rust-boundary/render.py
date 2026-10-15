"""Render actual Rust output faces; no reference-engine geometry operations."""
import json
from pathlib import Path
import sys
from bridge import HERE, clip, decode
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection


def draw(ax, boundary, title, cap_normal=None):
    for face in boundary.faces:
        points = [tuple(map(float, boundary.directed(u)[2].p0)) for u in face.loops[0]]
        cap = cap_normal and tuple(face.surface.normal) == cap_normal
        ax.add_collection3d(Poly3DCollection([points], facecolor="#ffb454" if cap else "#64a8d1",
                                            edgecolor="#183c54", linewidth=.9, alpha=.85))
    ax.set(xlim=(-.15, 2.15), ylim=(-.15, 2.15), zlim=(-.15, 2.15), title=title,
           xlabel="x (mm)", ylabel="y (mm)", zlabel="z (mm)")
    ax.set_box_aspect((1, 1, 1))
    ax.view_init(elev=24, azim=35)


if __name__ == "__main__":
    binary = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else HERE / "target/release/boundary-clip"
    data = json.loads((HERE / "fixtures/cube-oblique.request.json").read_text())
    original = decode(data["boundary"])
    _, left = clip(binary, original, (1, 1, 1), 3)
    _, right = clip(binary, original, (-1, -1, -1), -3)
    fig = plt.figure(figsize=(12, 4.5))
    draw(fig.add_subplot(131, projection="3d"), original, "Input: 8 mm³")
    draw(fig.add_subplot(132, projection="3d"), left, "x + y + z ≤ 3: 4 mm³", (1, 1, 1))
    draw(fig.add_subplot(133, projection="3d"), right, "Complement: 4 mm³", (-1, -1, -1))
    fig.suptitle("Custom Rust kernel · exact boundary clipping", fontsize=17)
    fig.tight_layout()
    fig.savefig(HERE / "boundary-clipping.png", dpi=180)
    fig.savefig(HERE / "boundary-clipping.svg")
    svg = HERE / "boundary-clipping.svg"
    svg.write_text("\n".join(line.rstrip() for line in svg.read_text().splitlines()) + "\n")
